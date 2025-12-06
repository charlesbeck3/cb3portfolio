import contextlib
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.db.models import F, Sum

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.views.generic import TemplateView

from portfolio.models import Account, AccountType, AssetClass, TargetAllocation, Holding
from portfolio.services import PortfolioSummaryService


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/index.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Get summary data
        context['summary'] = PortfolioSummaryService.get_holdings_summary(self.request.user)
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(self.request.user)

        # Add account types for the "Add Account" modal/form if needed,
        # or just passing them for display.
        # Previously: (code, label) for code, label in Account.ACCOUNT_TYPES
        # Now: Use AccountType model
        assert self.request.user.is_authenticated
        context['account_types'] = AccountType.objects.filter(accounts__user=self.request.user).distinct().values_list('code', 'label').order_by('label')

        return context


class HoldingsView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/holdings.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        account_id = kwargs.get('account_id')

        context.update(PortfolioSummaryService.get_holdings_by_category(self.request.user, account_id))
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(self.request.user)

        if account_id and self.request.user.is_authenticated:
                 with contextlib.suppress(Account.DoesNotExist):
                     context['account'] = Account.objects.get(id=account_id, user=self.request.user)

        return context


class TargetAllocationView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/target_allocations.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # 1. Get relevant Account Types (cols)
        # Only show account types that the user actually has accounts for? 
        # Or all available? Usually you only plan for what you have.
        account_types = AccountType.objects.filter(accounts__user=user).distinct().order_by('group__sort_order', 'label')
        
        # 2. Get Asset Classes and Calculate Values for Sorting
        asset_classes = AssetClass.objects.exclude(name='Cash').select_related('category', 'category__parent').all()
        
        # Calculate current value for each asset class to enable sorting AND per-account display
        # Map: asset_class_id -> total_value (Global)
        ac_values: dict[int, Decimal] = defaultdict(Decimal)
        
        # Map: account_type_id -> { key -> value } for aggregation
        # keys: "ac_{id}", "cat_{code}", "group_{code}"
        at_values: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        
        holdings = Holding.objects.filter(account__user=user).select_related('security', 'account__account_type')
        
        for h in holdings:
             if h.current_price:
                 val = h.shares * h.current_price
                 ac = h.security.asset_class
                 at_id = h.account.account_type_id
                 
                 # Global Asset Value
                 ac_values[ac.id] += val
                 
                 # Per-Account Asset Value
                 at_values[at_id][f'ac_{ac.id}'] += val
                 
                 # Per-Account Category Value
                 at_values[at_id][f'cat_{ac.category_id}'] += val
                 
                 # Per-Account Group Value
                 # Need to lookup group. Can we trust we have access to it here?
                 # ac.category is joined, but parent? 
                 # We selected related 'category' above, but h.security.asset_class does not auto-select category__parent unless we prefetch it on Holdings or lazily fetch.
                 # Optimization: Use the asset_classes query result to map ID -> Group Code?
                 pass

        # We need a map of AssetID -> (CategoryCode, GroupCode) to aggregate efficiently without N+1
        # Re-use the asset_classes loop below to fill this, OR do it first.
        # Let's do it efficiently.
        
        # 1. First pass asset classes to build hierarchy map
        ac_to_hierarchy = {}
        for ac in asset_classes:
            group = ac.category.parent if ac.category.parent else ac.category
            ac_to_hierarchy[ac.id] = (ac.category.code, group.code)
            
        # 2. Process Holdings using hierarchy map
        for h in holdings:
             if h.current_price:
                 val = h.shares * h.current_price
                 ac_id = h.security.asset_class_id
                 at_id = h.account.account_type_id
                 
                 ac_values[ac_id] += val
                 at_values[at_id][f'ac_{ac_id}'] += val
                 
                 if ac_id in ac_to_hierarchy:
                     cat_code, group_code = ac_to_hierarchy[ac_id]
                     at_values[at_id][f'cat_{cat_code}'] += val
                     at_values[at_id][f'group_{group_code}'] += val
        
        
        portfolio_total = sum(ac_values.values())
        portfolio_total_value = portfolio_total # alias
        
        # 3. Calculate Percentages for per-account map
        # current_allocations[at_id][key] = pct
        current_allocations: dict[int, dict[str, Decimal]] = defaultdict(dict)
        
        # We need sum of each account type to calc pct
        # We calculated this previously as `account_type_totals`. Let's reuse or recalculate.
        at_totals = defaultdict(Decimal)
        for at_id, val_dict in at_values.items():
            # Total for this AT is sum of its groups? or safer: sum of its assets
            # Let's sum assets
            curr_total = Decimal(0)
            for k, v in val_dict.items():
                if k.startswith('ac_'):
                    curr_total += v
            at_totals[at_id] = curr_total
            
        for at_id, val_dict in at_values.items():
            total = at_totals[at_id]
            if total > 0:
                for key, val in val_dict.items():
                    current_allocations[at_id][key] = (val / total) * 100
        
        # Build Tree with explicit objects for sorting & pct calculation
        def get_group(ac_obj):
            return ac_obj.category.parent if ac_obj.category.parent else ac_obj.category
            
        tree = {}
        
        for ac in asset_classes:
            ac_val = ac_values[ac.id]
            # Attach value and pct to ac object for sorting leaf nodes & display
            ac.total_value = ac_val 
            ac.current_pct = (ac_val / portfolio_total * 100) if portfolio_total > 0 else Decimal(0)
            ac.id_key = f"ac_{ac.id}" # Key for per-account lookup
            
            group = get_group(ac)
            category = ac.category
            
            if group not in tree:
                tree[group] = {'total': Decimal(0), 'categories': {}}
            
            group_node = tree[group]
            group_node['total'] += ac_val
            
            if category not in group_node['categories']:
                group_node['categories'][category] = {'total': Decimal(0), 'assets': []}
                
            cat_node = group_node['categories'][category]
            cat_node['total'] += ac_val
            cat_node['assets'].append(ac)
            
        # Sort Tree
        sorted_groups = sorted(tree.items(), key=lambda x: (x[1]['total'], x[0].label), reverse=True)
        
        hierarchical_data = [] # [(group, [(category, [assets])])]
        
        for group, group_data in sorted_groups:
            # Attach Group Pct & Key
            group.current_pct = (group_data['total'] / portfolio_total * 100) if portfolio_total > 0 else Decimal(0)
            group.code_key = f"group_{group.code}"
            
            # Sort categories
            sorted_cats = sorted(
                group_data['categories'].items(), 
                key=lambda x: (x[1]['total'], x[0].label), 
                reverse=True
            )
            
            cat_list = []
            for category, cat_data in sorted_cats:
                # Attach Category Pct & Key
                category.current_pct = (cat_data['total'] / portfolio_total * 100) if portfolio_total > 0 else Decimal(0)
                category.code_key = f"cat_{category.code}"
                
                # Sort assets
                sorted_assets = sorted(
                    cat_data['assets'],
                    key=lambda x: (x.total_value, x.name),
                    reverse=True
                )
                cat_list.append((category, sorted_assets))
            
            hierarchical_data.append((group, cat_list))
            
        # 3. Get existing Targets
        # Map: account_type_id -> {asset_class_id -> target_pct}
        # Use nested defaultdict for easy template access via custom filter
        # target_map[at_id][ac_id]
        existing_targets = TargetAllocation.objects.filter(user=user)
        target_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        for t in existing_targets:
            target_map[t.account_type_id][t.asset_class_id] = t.target_pct
            
        # 4. Calculate Total Value per Account Type for weighting
        # We already calculated this as at_totals above, using the same source (holdings)
        # So we can skip the second query.
        
        context['account_types'] = account_types
        context['hierarchical_data'] = hierarchical_data
        context['target_map'] = target_map
        context['current_allocations'] = current_allocations
        context['account_type_totals'] = at_totals
        context['portfolio_total_value'] = portfolio_total
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(user)
        
        return context

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        user = request.user
        account_types = AccountType.objects.filter(accounts__user=user).distinct()
        
        try:
            cash_ac = AssetClass.objects.get(name='Cash')
        except AssetClass.DoesNotExist:
             messages.error(request, "Cash asset class not found. Please contact support.")
             return redirect('portfolio:target_allocations')

        # Assets inputs (exclude Cash)
        input_asset_classes = list(AssetClass.objects.exclude(name='Cash').all())
        
        # All assets for saving (include Cash)
        save_asset_classes = input_asset_classes + [cash_ac]
        
        # Data structure to collect updates before saving
        # account_type_id -> {asset_class_id: decimal_value}
        updates: dict[int, dict[int, Decimal]] = defaultdict(dict)
        
        try:
            # 1. Extract and Validate Input
            for at in account_types:
                total_pct = Decimal('0.00')
                for ac in input_asset_classes:
                    key = f"target_{at.id}_{ac.id}"
                    val_str = request.POST.get(key, '').strip()
                    
                    if not val_str:
                        continue
                        
                    try:
                        val = Decimal(val_str)
                    except ValueError:
                        # Invalid number provided
                         messages.error(request, f"Invalid value for {at.label} - {ac.name}")
                         return redirect('portfolio:target_allocations')
                    
                    if val < 0:
                        messages.error(request, "Negative allocations are not allowed.")
                        return redirect('portfolio:target_allocations')
                        
                    updates[at.id][ac.id] = val
                    total_pct += val
                
                # Check total > 100 with tolerance
                if total_pct > Decimal('100.00') + Decimal('0.01'):
                    messages.error(request, f"Total allocation for {at.label} exceeds 100% ({total_pct}%)")
                    return redirect('portfolio:target_allocations')
                
                # Calculate Cash Residual
                cash_residual = Decimal('100.00') - total_pct
                # Avoid negative zero or tiny precision issues
                if cash_residual < Decimal('0.00'): 
                    cash_residual = Decimal('0.00')
                    
                updates[at.id][cash_ac.id] = cash_residual

            # 2. Persist Updates
            with transaction.atomic():
                current_targets = TargetAllocation.objects.filter(user=user).select_related('account_type', 'asset_class')
                # Map for quick lookup: (account_type_id, asset_class_id) -> obj
                target_obj_map = {(t.account_type_id, t.asset_class_id): t for t in current_targets}
                
                for at in account_types:
                    for ac in save_asset_classes:
                        val = updates[at.id].get(ac.id, Decimal('0.00'))
                        key = (at.id, ac.id)
                        
                        if val > 0:
                            if key in target_obj_map:
                                # Update existing
                                obj = target_obj_map[key]
                                if obj.target_pct != val:
                                    obj.target_pct = val
                                    obj.save()
                            else:
                                # Create new
                                TargetAllocation.objects.create(
                                    user=user,
                                    account_type=at,
                                    asset_class=ac,
                                    target_pct=val
                                )
                        else:
                            # If value is 0 (or missing which defaults to 0), delete if exists
                            if key in target_obj_map:
                                target_obj_map[key].delete()

            messages.success(request, "Target allocations updated successfully.")
            return redirect('portfolio:target_allocations')

        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
            return redirect('portfolio:target_allocations')

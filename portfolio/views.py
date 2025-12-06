import contextlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views.generic import TemplateView

from portfolio.models import Account, AccountType, AssetCategory, AssetClass, Holding, TargetAllocation
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


class AllocationsView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/allocations.html'
    
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        
        # We can reuse the hierarchical structure builder or just pass raw assets
        # For the read-only view, maybe listing by category is enough.
        # Let's reuse the logic from TargetAllocationView ideally, but for now
        # let's just pass summary.
        
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(self.request.user)
        return context


class TargetAllocationView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/target_allocations.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        if not user.is_authenticated:
            return context
            
        # Cast user so mypy knows they are authenticated for ORM usage
        user = cast(Any, user)

        # 1. Get Targets
        targets = TargetAllocation.objects.filter(user=user).select_related('account_type', 'asset_class')
        
        # Determine existing target percentage map
        # map: account_type_id -> asset_class_id -> target_pct
        target_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        existing_targets = list(targets)
        for t in existing_targets:
            target_map[t.account_type_id][t.asset_class_id] = t.target_pct
            
        # 2. Get Current Holdings / Market Values
        holdings = Holding.objects.filter(account__user=user).select_related('security__asset_class', 'account__account_type')
        
        # Aggregations
        ac_values: dict[int, Decimal] = defaultdict(Decimal)
        at_values: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        
        for h in holdings:
            if h.current_price:
                 val = h.shares * h.current_price
                 ac = h.security.asset_class
                 at_id = h.account.account_type_id
                 
                 ac_values[ac.id] += val
                 at_values[at_id][f'ac_{ac.id}'] += val
                 at_values[at_id][f'cat_{ac.category_id}'] += val
                 
                 # Group aggregation handled if needed, or via helper
                 if ac.category.parent:
                      at_values[at_id][f'group_{ac.category.parent_id}'] += val
                 else:
                      at_values[at_id][f'group_{ac.category_id}'] += val

        asset_classes = AssetClass.objects.exclude(name='Cash').select_related('category', 'category__parent').all()
        account_types = AccountType.objects.filter(accounts__user=user).distinct().order_by('group__sort_order', 'label')

        portfolio_total = sum(ac_values.values())
        
        # 3. Calculate Percentages for per-account map
        current_allocations: dict[int, dict[str, Decimal]] = defaultdict(dict)
        
        at_totals = defaultdict(Decimal)
        for at_id, val_dict in at_values.items():
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
        
        # Build Tree
        def get_group(ac_obj: AssetClass) -> AssetCategory:
            return ac_obj.category.parent if ac_obj.category.parent else ac_obj.category
            
        tree: dict[AssetCategory, dict[str, Any]] = {}
        
        for ac in asset_classes:
            ac_val = ac_values[ac.id]
            # Attach value and pct to ac object for sorting leaf nodes & display
            ac.total_value = ac_val  # type: ignore
            ac.current_pct = (ac_val / portfolio_total * 100) if portfolio_total > 0 else Decimal(0) # type: ignore
            ac.id_key = f"ac_{ac.id}" # type: ignore # Key for per-account lookup
            
            group = get_group(ac)
            category = ac.category
            
            if group not in tree:
                tree[group] = {'total': Decimal(0), 'categories': {}}
            
            group_node = tree[group]
            group_node['total'] += ac_val
            
            group_categories: dict[AssetCategory, dict[str, Any]] = group_node['categories']
            
            if category not in group_categories:
                group_categories[category] = {'total': Decimal(0), 'assets': []}
                
            cat_node = group_categories[category]
            cat_node['total'] += ac_val
            cat_node['assets'].append(ac)
        
        # Sort Tree
        sorted_groups = sorted(tree.items(), key=lambda x: (x[1]['total'], x[0].label), reverse=True)
        
        hierarchical_data = [] # [(group, [(category, [assets])])]
        
        for group, group_data in sorted_groups:
            group.current_pct = (group_data['total'] / portfolio_total * 100) if portfolio_total > 0 else Decimal(0) # type: ignore
            group.code_key = f"group_{group.code}" # type: ignore
            
            sorted_cats = sorted(
                group_data['categories'].items(), 
                key=lambda x: (x[1]['total'], x[0].label), 
                reverse=True
            )
            
            cat_list = []
            for category, cat_data in sorted_cats:
                category.current_pct = (cat_data['total'] / portfolio_total * 100) if portfolio_total > 0 else Decimal(0)
                category.code_key = f"cat_{category.code}"
                
                sorted_assets = sorted(
                    cat_data['assets'],
                    key=lambda x: (x.total_value, x.name),
                    reverse=True
                )
                cat_list.append((category, sorted_assets))
            
            hierarchical_data.append((group, cat_list))

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
        if not user.is_authenticated:
            return redirect('login')
            
        user = cast(Any, user) # Cast for ORM

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
        updates: dict[int, dict[int, Decimal]] = defaultdict(dict)
        
        try:
            # 1. Extract and Validate Input
            for at in account_types:
                total_pct = Decimal('0.00')
                for ac in input_asset_classes:
                    input_key = f"target_{at.id}_{ac.id}"
                    val_str = request.POST.get(input_key, '').strip()
                    
                    if not val_str:
                        continue
                        
                    try:
                        val = Decimal(val_str)
                    except ValueError:
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
                if cash_residual < Decimal('0.00'): 
                    cash_residual = Decimal('0.00')
                    
                updates[at.id][cash_ac.id] = cash_residual

            # 2. Persist Updates
            with transaction.atomic():
                current_targets = TargetAllocation.objects.filter(user=user).select_related('account_type', 'asset_class')
                target_obj_map = {(t.account_type_id, t.asset_class_id): t for t in current_targets}
                
                for at in account_types:
                    for ac in save_asset_classes:
                        val = updates[at.id].get(ac.id, Decimal('0.00'))
                        lookup_key = (at.id, ac.id)
                        
                        if val > 0:
                            if lookup_key in target_obj_map:
                                # Update existing
                                obj = target_obj_map[lookup_key]
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
                            # Delete if exists
                            if lookup_key in target_obj_map:
                                target_obj_map[lookup_key].delete()

            messages.success(request, "Target allocations updated successfully.")
            return redirect('portfolio:target_allocations')

        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
            return redirect('portfolio:target_allocations')

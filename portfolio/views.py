import contextlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views.generic import TemplateView

from portfolio.models import (
    Account,
    AccountType,
    AssetCategory,
    AssetClass,
    Holding,
    TargetAllocation,
)
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

    def post(self, request: Any, **kwargs: Any) -> Any:
        account_id = kwargs.get('account_id')
        if not account_id:
            messages.error(request, "Can only edit holdings for a specific account.")
            return redirect('portfolio:holdings')

        try:
            account = Account.objects.get(id=account_id, user=request.user)
        except Account.DoesNotExist:
            messages.error(request, "Account not found.")
            return redirect('portfolio:holdings')

        # Track updates
        updates_count = 0

        # Iterate over POST data
        for key, value in request.POST.items():
            if not value:
                continue

            if key.startswith('shares_'):
                ticker = key.replace('shares_', '')
                try:
                    shares = Decimal(value)
                    # Find holding
                    holding = Holding.objects.filter(account=account, security__ticker=ticker).first()
                    if holding:
                        holding.shares = shares
                        holding.save()
                        updates_count += 1
                except (ValueError, IndexError):
                    pass

        if updates_count > 0:
            messages.success(request, f"Updated {updates_count} holdings.")
        else:
            messages.info(request, "No changes saved.")

        return redirect('portfolio:account_holdings', account_id=account_id)


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

        user = cast(Any, user)

        # 1. Get Targets
        targets = TargetAllocation.objects.filter(user=user).select_related('account_type', 'asset_class', 'account')

        # Structure:
        # defaults: at_id -> ac_id -> pct
        # overrides: account_id -> ac_id -> pct
        defaults_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        overrides_map: dict[int, dict[int, Decimal]] = defaultdict(dict)

        for t in targets:
            if t.account_id:
                overrides_map[t.account_id][t.asset_class_id] = t.target_pct
            else:
                defaults_map[t.account_type_id][t.asset_class_id] = t.target_pct

        # 2. Get Current Holdings / Market Values & Build Accounts Hierarchy
        holdings = Holding.objects.filter(account__user=user).select_related('security__asset_class', 'account__account_type')

        # We need to calculate percentages for:
        # a) Account Types (Aggregate)
        # b) Individual Accounts

        # Account Values and Aggregation
        # account_values: account_id -> total_value
        # account_ac_values: account_id -> ac_id -> value
        account_values: dict[int, Decimal] = defaultdict(Decimal)
        account_ac_values: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

        # Account Type Aggregation
        at_values: dict[int, Decimal] = defaultdict(Decimal) # Total value
        at_ac_values: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

        for h in holdings:
            if h.current_price:
                 val = h.shares * h.current_price
                 ac_id = h.security.asset_class_id
                 at_id = h.account.account_type_id
                 acc_id = h.account.id

                 account_values[acc_id] += val
                 account_ac_values[acc_id][ac_id] += val

                 at_values[at_id] += val
                 at_ac_values[at_id][ac_id] += val

        asset_classes = AssetClass.objects.exclude(name='Cash').select_related('category', 'category__parent').all()
        # Prefetch accounts grouped by type
        account_types_qs = AccountType.objects.filter(accounts__user=user).distinct().order_by('group__sort_order', 'label')

        account_types = []
        for at_obj in account_types_qs:
            at: Any = at_obj
            # Attach accounts to account type for template iteration
            at_accounts = list(Account.objects.filter(user=user, account_type=at))
            # Calculate current percentages for each account
            for acc_obj in at_accounts:
                acc: Any = acc_obj
                total = account_values[acc.id]
                acc.current_total_value = total
                acc.allocation_map = {}
                if total > 0:
                     for ac_id, val in account_ac_values[acc.id].items():
                         acc.allocation_map[ac_id] = (val / total) * 100

                # Attach overrides context
                acc.target_map = overrides_map.get(acc.id, {})

            at.active_accounts = at_accounts
            at.current_total_value = at_values[at.id]
            at.allocation_map = {}
            if at.current_total_value > 0:
                for ac_id, val in at_ac_values[at.id].items():
                    at.allocation_map[ac_id] = (val / at.current_total_value) * 100

            # Attach defaults context
            at.target_map = defaults_map.get(at.id, {})

            account_types.append(at)

        # Build Hierarchical Asset Data (Row Structure)
        # We reuse the logic but now we don't need detailed calculations in the view
        # as much as structuring for the recursive table matching index.html style?
        # Actually target_allocations.html is a grid. Asset Classes (Rows) x Account Types (Cols).
        # We need to inject Accounts as sub-columns or expandables.

        # Build Hierarchical Asset Data (Row Structure) with Sorting and Subtotals

        def get_group(ac_obj: AssetClass) -> AssetCategory:
            return ac_obj.category.parent if ac_obj.category.parent else ac_obj.category

        # 1. Calculate Totals for Sorting
        # asset_totals: ac_id -> total_value
        asset_totals: dict[int, Decimal] = defaultdict(Decimal)
        # category_totals: category_obj -> total_value
        category_totals: dict[AssetCategory, Decimal] = defaultdict(Decimal)

        for _, ac_data in at_ac_values.items():
            for ac_id, val in ac_data.items():
                asset_totals[ac_id] += val

        # 2. Build Tree
        tree: dict[AssetCategory, dict[str, Any]] = {}

        for ac_obj in asset_classes:
            ac: Any = ac_obj
            group = get_group(ac)
            category = ac.category

            # Populate totals
            ac_total = asset_totals.get(ac.id, Decimal(0))
            category_totals[category] += ac_total
            # Note: We aren't explicitly summing group totals for sorting here but could if needed.
            # Groups usually have fixed sort order (Investments vs Retirement etc is usually Account Group,
            # but here it's Asset Group likely by name/order). AssetCategory model has 'ordering'.

            if group not in tree:
                tree[group] = {'categories': {}, 'total_value': Decimal(0)}

            group_node = tree[group]
            if category not in group_node['categories']:
                group_node['categories'][category] = {
                    'assets': [],
                    'total_value': Decimal(0),
                    # Pre-calculate category-level aggregates for the subtotal row
                    'allocation_map': defaultdict(Decimal), # at_id -> pct sum (approx)
                    'account_allocation_map': defaultdict(Decimal) # acc_id -> pct sum (approx)
                }

            # Add asset to category
            # We attach the total value to the asset object for easy sorting access later
            ac.current_total_value = ac_total
            group_node['categories'][category]['assets'].append(ac)

            # Update Node Totals
            group_node['categories'][category]['total_value'] += ac_total
            group_node['total_value'] += ac_total

            # 3. Pre-calculate Category Subtotal Percentages (Sum of Constituent Assets)
            # Iterate through Account Types and Accounts to sum their allocations for this category
            cat_node = group_node['categories'][category]

            # Account Types
            for at in account_types:
                 current_at_val = at_ac_values[at.id].get(ac.id, Decimal(0))
                 if at.current_total_value > 0:
                      pct = (current_at_val / at.current_total_value) * 100
                      cat_node['allocation_map'][at.id] += pct

            # Individual Accounts
            for at in account_types:
                 for acc in at.active_accounts:
                      current_acc_val = account_ac_values[acc.id].get(ac.id, Decimal(0))
                      if acc.current_total_value > 0:
                           pct = (current_acc_val / acc.current_total_value) * 100
                           cat_node['account_allocation_map'][acc.id] += pct


        # 4. Sort Tree
        # Sort Groups (Keep alphabetical or model ordering? Model ordering is safest for Groups)
        # Using label for now as before, or explicit sort if available.

        hierarchical_data = []

        # Sort Groups (Primary Level) - usually static/alphabetical is fine, or by total value?
        # Requirement: "Use the same sort descending approach for asset categories and then asset classes"
        # Let's sort Groups by total value descending too for consistency, or keep label if "Asset Categories" was the specific request.
        # User said "sort descending approach for asset categories and then asset classes". Implicitly Groups might behave same.

        sorted_groups = sorted(tree.items(), key=lambda x: x[1]['total_value'], reverse=True)

        for group, group_data in sorted_groups:
             cat_list = []

             # Sort Categories by Total Value Descending
             sorted_categories = sorted(
                 group_data['categories'].items(),
                 key=lambda x: x[1]['total_value'],
                 reverse=True
             )

             for category, cat_data in sorted_categories:
                  # Sort Assets by Total Value Descending
                  sorted_assets = sorted(
                      cat_data['assets'],
                      key=lambda x: x.current_total_value,
                      reverse=True
                  )

                  # Pack data for template
                  cat_info = {
                      'obj': category,
                      'total_value': cat_data['total_value'],
                      'allocation_map': cat_data['allocation_map'],
                      'account_allocation_map': cat_data['account_allocation_map']
                  }

                  cat_list.append((cat_info, sorted_assets))

             hierarchical_data.append((group, cat_list))

        context['account_types'] = account_types
        context['hierarchical_data'] = hierarchical_data

        # Calculate Portfolio Total
        portfolio_total = sum(at_values.values())
        context['portfolio_total_value'] = portfolio_total
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(user)

        # Pass defaults map for calculating inherited values in JS if needed
        # {at_id: {ac_id: pct}}
        context['defaults_map'] = defaults_map

        # Add Cash Asset ID for template lookups
        try:
             cash_ac = AssetClass.objects.get(name='Cash')
             context['cash_asset_class_id'] = cash_ac.id
        except AssetClass.DoesNotExist:
             context['cash_asset_class_id'] = None

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
             messages.error(request, "Cash asset class not found.")
             return redirect('portfolio:target_allocations')

        input_asset_classes = list(AssetClass.objects.exclude(name='Cash').all())


        # We need to process inputs for:
        # 1. Defaults (Account Type level): target_{at_id}_{ac_id}
        # 2. Overrides (Account level): target_account_{acc_id}_{ac_id}

        # Structure for updates:
        # Defaults: at_id -> ac_id -> val
        # Overrides: acc_id -> ac_id -> val

        default_updates: dict[int, dict[int, Decimal]] = defaultdict(dict)
        override_updates: dict[int, dict[int, Decimal]] = defaultdict(dict)

        # Validation Errors
        errors = []

        # 1. Process Account Types (Defaults)
        for at in account_types:
            total_pct = Decimal('0.00')
            for ac in input_asset_classes:
                input_key = f"target_{at.id}_{ac.id}"
                val_str = request.POST.get(input_key, '').strip()

                # Defaults must have value? Or if empty assume 0?
                # Let's assume empty = 0 for defaults to simplify
                val = Decimal('0.00')
                if val_str:
                    try:
                        val = Decimal(val_str)
                    except ValueError:
                         errors.append(f"Invalid value for {at.label} - {ac.name}")

                if val < 0:
                    errors.append(f"Negative allocation for {at.label}")

                default_updates[at.id][ac.id] = val
                total_pct += val

            # Cash Residual
            cash_residual = Decimal('100.00') - total_pct
            if cash_residual < 0:
                 # Allow slight tolerance?
                 if cash_residual < Decimal('-0.01'):
                      errors.append(f"Total allocation for {at.label} exceeds 100% ({total_pct}%)")
                 cash_residual = Decimal('0.00')

            default_updates[at.id][cash_ac.id] = cash_residual

        # 2. Process Accounts (Overrides)
        # We need to iterate over all accounts for these types
        accounts = Account.objects.filter(user=user)

        for acc in accounts:
            # Start with implicit assumption: No override.
            # If user entered something, it's an override.
            # If user cleared an existing override, it's a deletion.
            # Ideally frontend sends explicit fields.

            # We track if current account has ANY overrides provided in this POST.
            # If a row is hidden/not rendered, maybe we shouldn't touch it?
            # But this is a full form save.

            # Check for input presence? The inputs exist in DOM.

            # Accumulate totals to check 100% if we are setting overrides?
            # If setting PARTIAL overrides, what happens?
            # Rule: If you override ONE asset class, do you have to override ALL?
            # Complex.
            # Simplest logic: Overrides are per asset class.
            # But constraints: Total of (Effective Targets) must be 100%.
            # If I override Equity to 60% (Default 50%), where does the extra 10% come from?
            # It must come from Cash or another asset.
            # This implies if you override, you might break the 100% sum unless the system auto-adjusts Cash?
            # Let's apply the same "Cash Residual" logic to Overrides IF there are overrides.

            # Actually, to correctly calculate Cash Residual for an account, we need its EFFECTIVE mix.
            # Effective Mix = Override if exists else Default.
            # So calculating updates requires combining Defaults + Inputs.

            # FULL OVERRIDE LOGIC IMPLEMENTATION
            # If ANY override is provided for an account, we treat it as a "Custom Strategy" account.
            # This means we DO NOT fallback to defaults for unspecified asset classes.
            # Unspecified asset classes are assumed to be 0%.

            # 1. Identify if this account has ANY explicit input provided (Standard or Cash)
            has_explicit_input = False

            # Check Standard Assets
            for ac in input_asset_classes:
                input_key = f"target_account_{acc.id}_{ac.id}"
                val_str = request.POST.get(input_key, '').strip()
                if val_str:
                    has_explicit_input = True
                    break

            # Check Cash
            if not has_explicit_input:
                cash_input_key = f"target_account_{acc.id}_{cash_ac.id}"
                if request.POST.get(cash_input_key, '').strip():
                    has_explicit_input = True

            if has_explicit_input:
                # Full Override Mode
                effective_values = {}

                # Process Standard Assets
                for ac in input_asset_classes:
                    input_key = f"target_account_{acc.id}_{ac.id}"
                    val_str = request.POST.get(input_key, '').strip()

                    if val_str:
                        try:
                            val = Decimal(val_str)
                            override_updates[acc.id][ac.id] = val
                            effective_values[ac.id] = val
                        except ValueError:
                            errors.append(f"Invalid value for {acc.name} - {ac.name}")
                    else:
                        # Explicitly 0 if not provided in Full Override Mode
                        # We don't need to save 0 explicitly if we clean up old overrides correctly.
                        # But for effective calculation, it's 0.
                        effective_values[ac.id] = Decimal('0.00')

                # Process Cash
                cash_input_key = f"target_account_{acc.id}_{cash_ac.id}"
                cash_val_str = request.POST.get(cash_input_key, '').strip()

                total_standard = sum(effective_values.values())

                if cash_val_str:
                    try:
                        cash_val = Decimal(cash_val_str)
                        override_updates[acc.id][cash_ac.id] = cash_val
                        # Validation: Sum should be close to 100
                        if abs(total_standard + cash_val - Decimal('100.00')) > Decimal('0.1'):
                             # Warning or Error? Let's just warn but save.
                             # Actually UI shows warning.
                             pass
                    except ValueError:
                         errors.append(f"Invalid value for {acc.name} - Cash")
                else:
                    # Implicit Residual Cash in Full Override Mode
                    # If user just said "Stocks 60", Cash is 40.
                    cash_residual = Decimal('100.00') - total_standard
                    if cash_residual < 0:
                         # Over-allocated?
                         pass
                    # We save this residual explicitly as an override because we are in Full Override mode
                    # and we want to lock it in vs defaults.
                    override_updates[acc.id][cash_ac.id] = max(Decimal('0.00'), cash_residual)

            else:
                # No Override Mode - Account follows Defaults purely.
                # We don't save anything to override_updates.
                # Existing overrides will be wiped in the cleanup step.
                pass

        if errors:
            for err in errors:
                messages.error(request, err)
            return redirect('portfolio:target_allocations')

        # 3. Persist
        try:
            with transaction.atomic():
                # save defaults
                current_defaults = TargetAllocation.objects.filter(user=user, account__isnull=True)
                default_map_obj = {(t.account_type_id, t.asset_class_id): t for t in current_defaults}

                for at_id, ac_map in default_updates.items():
                    for ac_id, val in ac_map.items():
                         lookup = (at_id, ac_id)
                         if val >= 0: # Should be true
                              if lookup in default_map_obj:
                                   obj = default_map_obj[lookup]
                                   if obj.target_pct != val:
                                        obj.target_pct = val
                                        obj.save()
                                   # Remove from map to track processed
                                   del default_map_obj[lookup]
                              else:
                                   TargetAllocation.objects.create(
                                        user=user,
                                        account_type_id=at_id,
                                        asset_class_id=ac_id,
                                        target_pct=val
                                   )

                # Delete stale defaults?
                # (Asset classes not in save list? We iterates all non-cash + cash, so should be fine)
                # But if asset classes were removed from system? (Unlikely)

                # Save Overrides
                # Logic: We have a map of overrides explicitly set or auto-calculated (cash).
                # All other existing overrides for this account/asset that are NOT in map should be DELETED (reset to default).

                current_overrides = TargetAllocation.objects.filter(user=user, account__isnull=False)
                override_obj_map = {(cast(int, t.account_id), t.asset_class_id): t for t in current_overrides}

                processed_overrides = set()

                for acc_id, ac_map in override_updates.items():
                    for ac_id, val in ac_map.items():
                         lookup = (acc_id, ac_id)
                         processed_overrides.add(lookup)

                         if lookup in override_obj_map:
                              obj = override_obj_map[lookup]
                              if obj.target_pct != val:
                                   obj.target_pct = val
                                   obj.save()
                         else:
                              TargetAllocation.objects.create(
                                   user=user,
                                   account_type_id=Account.objects.get(id=acc_id).account_type_id, # Optimization possible
                                   account_id=acc_id,
                                   asset_class_id=ac_id,
                                   target_pct=val
                              )

                # Delete Unused Overrides (keys in DB but not in our update map)
                # Note: We iterated ALL accounts. If an account had overrides before but now map is empty (user cleared inputs),
                # they will not be in override_updates.
                # So we iterate all existing overrides and check if they are in processed list.

                for lookup, obj in override_obj_map.items():
                     if lookup not in processed_overrides:
                          obj.delete()

            messages.success(request, "Allocations updated.")
            return redirect('portfolio:target_allocations')

        except Exception as e:
            messages.error(request, f"Error saving targets: {e}")
            return redirect('portfolio:target_allocations')


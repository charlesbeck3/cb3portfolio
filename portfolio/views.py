import contextlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views.generic import TemplateView

from portfolio.context_builders import AllocationTableBuilder
from portfolio.forms import TargetAllocationForm
from portfolio.mixins import PortfolioContextMixin
from portfolio.models import (
    Account,
    AccountType,
    AssetClass,
    Holding,
    Security,
    TargetAllocation,
)


class DashboardView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        assert user.is_authenticated

        # 1. Get Targets (needed for displaying target values even in read-only)
        targets = TargetAllocation.objects.filter(user=user).select_related(
            "account_type", "asset_class", "account"
        )

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

        # 2. Get Summary Data via shared services
        services = self.get_portfolio_services()
        summary_service = services["summary"]

        summary = summary_service.get_holdings_summary(user)
        context["summary"] = summary

        # Sidebar data
        sidebar_data = summary_service.get_account_summary(user)
        context["sidebar_data"] = sidebar_data

        # 3. Build Account Types with lightweight context
        account_types_qs = (
            AccountType.objects.filter(accounts__user=user)
            .distinct()
            .order_by("group__sort_order", "label")
        )

        at_totals = summary.account_type_grand_totals
        rich_account_types: list[Any] = []
        for at_obj in account_types_qs:
            at: Any = at_obj
            at.current_total_value = at_totals.get(at.code, Decimal("0.00"))
            at.target_map = defaults_map.get(at.id, {})
            rich_account_types.append(at)

        context["account_types"] = rich_account_types

        cash_ac = AssetClass.objects.filter(name="Cash").first()
        context["cash_asset_class_id"] = cash_ac.id if cash_ac else None

        # Calculate 'Portfolio Total Value' for template usage
        context["portfolio_total_value"] = summary.grand_total

        builder = AllocationTableBuilder()
        context["allocation_rows_money"] = builder.build_rows(
            summary=summary,
            account_types=rich_account_types,
            portfolio_total_value=summary.grand_total,
            mode="money",
            cash_asset_class_id=context["cash_asset_class_id"],
        )
        context["allocation_rows_percent"] = builder.build_rows(
            summary=summary,
            account_types=rich_account_types,
            portfolio_total_value=summary.grand_total,
            mode="percent",
            cash_asset_class_id=context["cash_asset_class_id"],
        )

        return context


class HoldingsView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/holdings.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        account_id = kwargs.get("account_id")

        user = self.request.user
        assert user.is_authenticated

        services = self.get_portfolio_services()
        summary_service = services["summary"]

        context.update(summary_service.get_holdings_by_category(user, account_id))
        context.update(self.get_sidebar_context(user))

        if account_id and self.request.user.is_authenticated:
            with contextlib.suppress(Account.DoesNotExist):
                context["account"] = Account.objects.get(id=account_id, user=self.request.user)
                # Pass securities for the "Add Holding" modal
                context["securities"] = Security.objects.all().order_by("ticker")

        return context

    def post(self, request: Any, **kwargs: Any) -> Any:
        account_id = kwargs.get("account_id")
        if not account_id:
            messages.error(request, "Can only edit holdings for a specific account.")
            return redirect("portfolio:holdings")

        try:
            account = Account.objects.get(id=account_id, user=request.user)
        except Account.DoesNotExist:
            messages.error(request, "Account not found.")
            return redirect("portfolio:holdings")

        # Track updates
        updates_count = 0

        # Check for Add Holding
        security_id = request.POST.get("security_id")
        if security_id:
            initial_shares_str = request.POST.get("initial_shares", "0")
            try:
                initial_shares = Decimal(initial_shares_str)
                if initial_shares > 0:
                    security = Security.objects.get(id=security_id)

                    # Create or Get Holding
                    holding, created = Holding.objects.get_or_create(
                        account=account, security=security, defaults={"shares": initial_shares}
                    )

                    if not created:
                        messages.warning(
                            request,
                            f"Holding for {security.ticker} already exists. Please edit shares instead.",
                        )
                    else:
                        messages.success(request, f"Added {security.ticker} to account.")
            except Security.DoesNotExist:
                messages.error(request, "Security not found.")
            except Exception as e:
                messages.error(request, f"Error adding holding: {e}")

            return redirect("portfolio:account_holdings", account_id=account_id)

        # Check for Delete Holding
        delete_ticker = request.POST.get("delete_ticker")
        if delete_ticker:
            delete_ticker = delete_ticker.strip().upper()
            try:
                holding_to_delete = Holding.objects.filter(
                    account=account, security__ticker=delete_ticker
                ).first()
                if holding_to_delete:
                    holding_to_delete.delete()
                    messages.success(request, f"Removed {delete_ticker} from account.")
                else:
                    messages.error(request, f"Holding {delete_ticker} not found.")
            except Exception as e:
                messages.error(request, f"Error deleting holding: {e}")

            return redirect("portfolio:account_holdings", account_id=account_id)

        # Iterate over POST data (Edit Logic)

        # Iterate over POST data
        for key, value in request.POST.items():
            if not value:
                continue

            if key.startswith("shares_"):
                ticker = key.replace("shares_", "")
                try:
                    shares = Decimal(value)
                    # Find holding
                    # Mypy issue: variable reuse? Let's use a specific name or ensure type.
                    # 'holding' was used above in the add block.
                    # It's better to verify scope. The 'add' block returns, so we are safe,
                    # but mypy might check the whole function scope.
                    # Let's just cast or ignore if it's a simple 'Optional' issue,
                    # but the error was "Incompatible types in assignment (expression has type "Holding | None", variable has type "Holding")".
                    # This implies 'holding' was inferred as 'Holding' (not optional) somewhere?
                    # Ah, 'get_or_create' returns (Holding, bool), so 'holding' there is 'Holding'.
                    # Here 'first()' returns 'Holding | None'.
                    # So we should use a different variable name to avoid confusion.
                    target_holding = Holding.objects.filter(
                        account=account, security__ticker=ticker
                    ).first()
                    if target_holding:
                        target_holding.shares = shares
                        target_holding.save()
                        updates_count += 1
                except (ValueError, IndexError):
                    pass

        if updates_count > 0:
            messages.success(request, f"Updated {updates_count} holdings.")
        else:
            messages.info(request, "No changes saved.")

        return redirect("portfolio:account_holdings", account_id=account_id)


class AllocationsView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/allocations.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        user = self.request.user
        assert user.is_authenticated

        # Allocations view currently only needs sidebar data; delegate to mixin.
        context.update(self.get_sidebar_context(user))
        return context


class TargetAllocationView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/target_allocations.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_authenticated:
            return context

        user = cast(Any, user)

        # 1. Get Targets
        targets = TargetAllocation.objects.filter(user=user).select_related(
            "account_type", "asset_class", "account"
        )

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

        # 2. Get Summary Data via shared services
        services = self.get_portfolio_services()
        summary_service = services["summary"]

        summary = summary_service.get_holdings_summary(user)
        context["summary"] = summary

        # We need account_types for columns
        # The service summary has account_type_grand_totals keys which are codes.
        # But we need the objects for labels and to attach accounts.

        account_types_qs = (
            AccountType.objects.filter(accounts__user=user)
            .distinct()
            .order_by("group__sort_order", "label")
        )

        account_types = []

        # We need to compute/attach active_accounts context for the template columns
        # The service doesn't return full Account objects with their specific "current_total_value" attached in a way the template expects for COLUMNS
        # (Service aggregates them into the summary structure, but here we need to iterate columns).

        # Let's fetch accounts and attach them to account types as before
        accounts = Account.objects.filter(user=user).select_related("account_type")
        account_map = {a.id: a for a in accounts}

        # Calculate Account totals for the header/columns
        # Service provides 'sidebar_data' which has account totals.

        sidebar_data = summary_service.get_account_summary(user)
        context["sidebar_data"] = sidebar_data

        # Map account ID to total from sidebar data
        account_totals = {}
        for group in sidebar_data["groups"].values():
            for acc in group["accounts"]:
                account_totals[acc["id"]] = acc["total"]

        # Also need Account Type totals
        # Summary has account_type_grand_totals (by code)
        at_totals = summary.account_type_grand_totals

        # Map of AccountType.id -> total value, used by frontend JS for Wt. Target calcs
        at_values: dict[int, Decimal] = {}

        for at_obj in account_types_qs:
            at: Any = at_obj
            at_accounts = [a for a in accounts if a.account_type_id == at.id]

            # Attach context expected by template
            at.current_total_value = at_totals.get(at.code, Decimal(0))
            at.target_map = defaults_map.get(at.id, {})

            # Expose totals by AccountType.id for JS (target_allocations.html -> at_values JSON)
            at_values[at.id] = at.current_total_value

            # Prepare accounts
            for acc in at_accounts:
                acc.current_total_value = account_totals.get(acc.id, Decimal(0))  # type: ignore
                acc.target_map = overrides_map.get(acc.id, {})  # type: ignore

            at.active_accounts = at_accounts
            account_types.append(at)

        # 3. Calculate detailed maps for Accounts and Types

        holdings = (
            Holding.objects.filter(account__user=user)
            .select_related("security", "account")
            .only("account_id", "security__asset_class_id", "shares", "current_price")
        )

        # account_id -> ac_id -> value
        account_ac_map: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        # at_id -> ac_id -> value
        at_ac_map: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

        for h in holdings:
            if h.current_price:
                val = h.shares * h.current_price
                if val > 0:
                    ac_id = h.security.asset_class_id
                    acc_id = h.account.id
                    at_id = account_map[acc_id].account_type_id

                    account_ac_map[acc_id][ac_id] += val
                    at_ac_map[at_id][ac_id] += val

        # Now populate maps on objects
        # Map asset_class_id -> category_code helper
        ac_id_to_cat = {}
        for group in summary.groups.values():
            for cat_code, cat_data in group.categories.items():
                for _, ac_data in cat_data.asset_classes.items():
                    if ac_data.id:
                        ac_id_to_cat[ac_data.id] = cat_code

        for at in account_types:
            # Populate AT maps
            at.dollar_map = at_ac_map[at.id]
            at.allocation_map = {}
            if at.current_total_value > 0:
                for ac_id, val in at.dollar_map.items():
                    at.allocation_map[ac_id] = (val / at.current_total_value) * 100

            for acc in at.active_accounts:
                acc.dollar_map = account_ac_map[acc.id]
                acc.allocation_map = {}
                if acc.current_total_value > 0:
                    for ac_id, val in acc.dollar_map.items():
                        acc.allocation_map[ac_id] = (val / acc.current_total_value) * 100

                # Populate category map
                acc.category_map = defaultdict(Decimal)
                for ac_id, val in acc.dollar_map.items():
                    holding_cat_code = ac_id_to_cat.get(ac_id)
                    if holding_cat_code:
                        acc.category_map[holding_cat_code] += val

        context["account_types"] = account_types
        context["portfolio_total_value"] = summary.grand_total

        # Pass per-account-type totals for JS Wt. Target calculations
        context["at_values"] = at_values

        # Pass defaults map for calculating inherited values in JS if needed
        # {at_id: {ac_id: pct}}
        context["defaults_map"] = defaults_map

        # Add Cash Asset ID for template lookups
        # Get Cash Asset Class ID for template logic
        cash_ac = AssetClass.objects.filter(name="Cash").first()
        context["cash_asset_class_id"] = cash_ac.id if cash_ac else None

        return context

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        user = request.user
        if not user.is_authenticated:
            return redirect("login")

        user = cast(Any, user)  # Cast for ORM

        account_types = AccountType.objects.filter(accounts__user=user).distinct()

        try:
            cash_ac = AssetClass.objects.get(name="Cash")
        except AssetClass.DoesNotExist:
            messages.error(request, "Cash asset class not found.")
            return redirect("portfolio:target_allocations")

        input_asset_classes = list(AssetClass.objects.exclude(name="Cash").all())

        # Use a form to parse default (account-type) target inputs
        form = TargetAllocationForm(
            request.POST or None,
            account_types=account_types,
            asset_classes=input_asset_classes,
        )

        if not form.is_valid():
            for field, field_errors in form.errors.items():
                for err in field_errors:
                    messages.error(request, f"{field}: {err}")
            return redirect("portfolio:target_allocations")

        # We need to process inputs for:
        # 1. Defaults (Account Type level): target_{at_id}_{ac_id}
        # 2. Overrides (Account level): target_account_{acc_id}_{ac_id}

        # Structure for updates:
        # Defaults: at_id -> ac_id -> val
        # Overrides: acc_id -> ac_id -> val

        default_updates: dict[int, dict[int, Decimal]] = defaultdict(dict)
        override_updates: dict[int, dict[int, Decimal]] = defaultdict(dict)

        # Validation Errors (for overrides and cross-field checks)
        errors = []

        # 1. Process Account Types (Defaults) using parsed form data
        parsed_defaults = form.get_parsed_targets()

        for at in account_types:
            total_pct = Decimal("0.00")
            at_defaults = parsed_defaults.get(at.id, {})

            for ac in input_asset_classes:
                val = at_defaults.get(ac.id, Decimal("0.00"))

                # Mirror previous safeguards: disallow negatives
                if val < 0:
                    errors.append(f"Negative allocation for {at.label}")

                default_updates[at.id][ac.id] = val
                total_pct += val

            # Cash Residual
            cash_residual = Decimal("100.00") - total_pct
            if cash_residual < 0:
                # Allow slight tolerance?
                if cash_residual < Decimal("-0.01"):
                    errors.append(f"Total allocation for {at.label} exceeds 100% ({total_pct}%)")
                cash_residual = Decimal("0.00")

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
                val_str = request.POST.get(input_key, "").strip()
                if val_str:
                    has_explicit_input = True
                    break

            # Check Cash
            if not has_explicit_input:
                cash_input_key = f"target_account_{acc.id}_{cash_ac.id}"
                if request.POST.get(cash_input_key, "").strip():
                    has_explicit_input = True

            if has_explicit_input:
                # Full Override Mode
                effective_values = {}

                # Process Standard Assets
                for ac in input_asset_classes:
                    input_key = f"target_account_{acc.id}_{ac.id}"
                    val_str = request.POST.get(input_key, "").strip()

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
                        effective_values[ac.id] = Decimal("0.00")

                # Process Cash
                cash_input_key = f"target_account_{acc.id}_{cash_ac.id}"
                cash_val_str = request.POST.get(cash_input_key, "").strip()

                total_standard = sum(effective_values.values())

                if cash_val_str:
                    try:
                        cash_val = Decimal(cash_val_str)
                        override_updates[acc.id][cash_ac.id] = cash_val
                        # Validation: Sum should be close to 100
                        if abs(total_standard + cash_val - Decimal("100.00")) > Decimal("0.1"):
                            # Warning or Error? Let's just warn but save.
                            # Actually UI shows warning.
                            pass
                    except ValueError:
                        errors.append(f"Invalid value for {acc.name} - Cash")
                else:
                    # Implicit Residual Cash in Full Override Mode
                    # If user just said "Stocks 60", Cash is 40.
                    cash_residual = Decimal("100.00") - total_standard
                    if cash_residual < 0:
                        # Over-allocated?
                        pass
                    # We save this residual explicitly as an override because we are in Full Override mode
                    # and we want to lock it in vs defaults.
                    override_updates[acc.id][cash_ac.id] = max(Decimal("0.00"), cash_residual)

            else:
                # No Override Mode - Account follows Defaults purely.
                # We don't save anything to override_updates.
                # Existing overrides will be wiped in the cleanup step.
                pass

        if errors:
            for err in errors:
                messages.error(request, err)
            return redirect("portfolio:target_allocations")

        # 3. Persist
        try:
            with transaction.atomic():
                # save defaults
                current_defaults = TargetAllocation.objects.filter(user=user, account__isnull=True)
                default_map_obj = {
                    (t.account_type_id, t.asset_class_id): t for t in current_defaults
                }

                for at_id, ac_map in default_updates.items():
                    for ac_id, val in ac_map.items():
                        lookup = (at_id, ac_id)
                        if val >= 0:  # Should be true
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
                                    target_pct=val,
                                )

                # Delete stale defaults?
                # (Asset classes not in save list? We iterates all non-cash + cash, so should be fine)

                # Save Overrides
                # Logic: We have a map of overrides explicitly set or auto-calculated (cash).
                # All other existing overrides for this account/asset that are NOT in map should be DELETED (reset to default).

                current_overrides = TargetAllocation.objects.filter(
                    user=user, account__isnull=False
                )
                override_obj_map = {
                    (cast(int, t.account_id), t.asset_class_id): t for t in current_overrides
                }

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
                                account_type_id=Account.objects.get(
                                    id=acc_id
                                ).account_type_id,  # Optimization possible
                                account_id=acc_id,
                                asset_class_id=ac_id,
                                target_pct=val,
                            )

                # Delete Unused Overrides (keys in DB but not in our update map)
                # Note: We iterated ALL accounts. If an account had overrides before but now map is empty (user cleared inputs),
                # they will not be in override_updates.
                # So we iterate all existing overrides and check if they are in processed list.

                for lookup, obj in override_obj_map.items():
                    if lookup not in processed_overrides:
                        obj.delete()

            messages.success(request, "Allocations updated.")
            return redirect("portfolio:target_allocations")

        except Exception as e:
            messages.error(request, f"Error saving targets: {e}")
            return redirect("portfolio:target_allocations")

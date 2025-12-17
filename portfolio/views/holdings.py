from __future__ import annotations

import contextlib
from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

import pandas as pd

from portfolio.models import Account, Holding, Security
from portfolio.views.mixins import PortfolioContextMixin


class HoldingsView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/holdings.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        account_id = kwargs.get("account_id")

        user = self.request.user
        assert user.is_authenticated

        # Fetch Accounts to build DataFrame
        accounts_qs = Account.objects.filter(user=user).select_related("account_type__group", "institution")
        if account_id:
            accounts_qs = accounts_qs.filter(id=account_id)

        # Build Detailed DataFrame manually to capture Shares/Price
        # Legacy .to_dataframe() only provided Matrix Values.

        all_holdings = []
        # Pre-fetch for performance
        holdings_qs = Holding.objects.filter(
            account__in=accounts_qs
        ).select_related(
            'account', 'account__account_type', 'account__account_type__group',
            'security', 'security__asset_class', 'security__asset_class__category'
        )

        for h in holdings_qs:
            # Replicate hierarchical strings
            act_type_lbl = h.account.account_type.label
            act_cat_name = h.account.account_type.group.name

            # Asset Class stuff
            ac = h.security.asset_class
            ac_name = ac.name if ac else "Unclassified"
            ac_cat_lbl = ac.category.label if ac and ac.category else "Unclassified"

            all_holdings.append({
                "Account_ID": h.account_id,
                "Account_Name": h.account.name,
                "Account_Type": act_type_lbl,
                "Account_Category": act_cat_name,
                "Asset_Class": ac_name,
                "Asset_Category": ac_cat_lbl,
                "Security": h.security.ticker,
                "Security_Name": h.security.name,
                "Shares": float(h.shares),
                "Price": float(h.current_price) if h.current_price is not None else 0.0,
                "Value": float(h.market_value),
            })

        if all_holdings:
            holdings_df = pd.DataFrame(all_holdings)
        else:
            holdings_df = pd.DataFrame(columns=[
                "Account_ID", "Account_Name", "Account_Type", "Account_Category",
                "Asset_Class", "Asset_Category", "Security", "Security_Name",
                "Shares", "Price", "Value"
            ])

        # Build Effective Targets Map
        from portfolio.services.targets import TargetAllocationService
        effective_targets_map = TargetAllocationService.get_effective_targets(user)

        # Calculate Holdings Detail
        from portfolio.services.allocation_calculations import AllocationCalculationEngine
        engine = AllocationCalculationEngine()
        # Get detailed calc (merges targets)
        # Pass the DETAILED df now, not the Matrix one.
        holdings_detail_df = engine.calculate_holdings_detail(holdings_df, effective_targets_map)

        # Build Metadata Map for Builder
        # We need Asset Class Name -> Group/Category details
        from portfolio.models import AssetClass
        ac_qs = AssetClass.objects.select_related("category__parent").all()
        ac_meta = {}
        for ac in ac_qs:
            parent = ac.category.parent
            ac_meta[ac.name] = {
                "group_code": parent.code if parent else ac.category.code,
                "group_label": parent.label if parent else ac.category.label,
                "category_code": ac.category.code,
                "category_label": ac.category.label
            }

        context.update(self.get_sidebar_context())

        # Use Builder
        from portfolio.presenters.holdings import HoldingsTableBuilder

        builder = HoldingsTableBuilder()
        holdings_rows = builder.build_rows(
            holdings_detail_df=holdings_detail_df,
            ac_meta=ac_meta
        )
        context["holdings_rows"] = holdings_rows

        if account_id:
            with contextlib.suppress(Account.DoesNotExist):
                context["account"] = Account.objects.get(id=account_id, user=user)
                # Pass securities for the "Add Holding" modal
                context["securities"] = Security.objects.all().order_by("ticker")

                # New Engine Calculation for single account chart (reused logic or redundant?)
                # This seems to duplicate what `calculate_holdings_detail` did but summarizes for a chart?
                # The original code had a chart block here. Let's keep it but use the existing DF.

                try:
                    if not holdings_df.empty:
                        # Group by Asset Class (level 0 of columns)
                        # holdings_df columns: (Asset_Class, Asset_Category, Security)
                        by_asset_class = holdings_df.T.groupby(level="Asset_Class").sum().T

                        # Sum across the single account (row)
                        # holdings_df row index: (Type, Cat, Name, ID)
                        # We just want total per asset class
                        ac_totals = by_asset_class.sum(axis=0) # Series indexed by Asset_Class

                        total_val = float(ac_totals.sum())

                        if total_val > 0:
                            percentages = (ac_totals / total_val * 100)
                        else:
                            percentages = ac_totals * 0

                        # Create summary DataFrame
                        summary_df = pd.DataFrame({
                            'Asset_Class': ac_totals.index,
                            'Dollar_Amount': ac_totals.values,
                            'Percentage': percentages.values
                        })
                        context["account_allocation"] = summary_df.to_dict('records')
                        context["account_total_value"] = total_val
                except Exception as e:
                    print(f"Error in pandas calculation: {e}")

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

        # 1. Handle Add Holding
        if "security_id" in request.POST:
            return self._handle_add_holding(request, account)

        # 2. Handle Delete Holding
        if "delete_ticker" in request.POST:
            return self._handle_delete_holding(request, account)

        # 3. Handle Bulk Update
        return self._handle_bulk_update(request, account)

    def _handle_add_holding(self, request: Any, account: Account) -> Any:
        from portfolio.forms.holdings import AddHoldingForm

        form = AddHoldingForm(request.POST)
        if form.is_valid():
            security_id = form.cleaned_data["security_id"]
            initial_shares = form.cleaned_data["initial_shares"]
            security = Security.objects.get(id=security_id)

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
        else:
            for field, error_list in form.errors.items():
                for error in error_list:
                    messages.error(request, f"{field}: {error}")

        return redirect("portfolio:account_holdings", account_id=account.id)

    def _handle_delete_holding(self, request: Any, account: Account) -> Any:
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

        return redirect("portfolio:account_holdings", account_id=account.id)

    def _handle_bulk_update(self, request: Any, account: Account) -> Any:
        updates_count = 0
        for key, value in request.POST.items():
            if not value:
                continue

            if key.startswith("shares_"):
                ticker = key.replace("shares_", "")
                try:
                    shares = Decimal(value)
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

        return redirect("portfolio:account_holdings", account_id=account.id)

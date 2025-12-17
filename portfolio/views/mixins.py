from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from portfolio.models import Account
from portfolio.services.allocation_calculations import AllocationCalculationEngine


class PortfolioContextMixin:
    """Provides common portfolio context data for portfolio views."""

    request: HttpRequest

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Insert sidebar data into context."""
        context = super().get_context_data(**kwargs)  # type: ignore
        context.update(self.get_sidebar_context())
        return context

    def get_sidebar_context(self) -> dict[str, Any]:
        """Get sidebar data for all portfolio views."""

        user = self.request.user
        assert user.is_authenticated

        # Calculate Sidebar Data using Engine
        from collections import OrderedDict
        from decimal import Decimal

        import pandas as pd

        from portfolio.models import AccountGroup

        accounts = Account.objects.filter(user=user).select_related("portfolio", "account_type__group", "institution")
        # Reuse engine just for total value and efficient data if needed,
        # but for simple sidebar standard ORM is sufficient if we don't need real-time prices?
        # Legacy update_prices was called. Engine assumes prices are in DB.
        # We can use Engine to get total values if we want consistent rounding/logic.

        # Let's use Pandas for totals to match other views
        portfolios = list({acc.portfolio for acc in accounts if acc.portfolio})
        dfs = [p.to_dataframe() for p in portfolios]
        holdings_df = pd.concat(dfs) if dfs else pd.DataFrame()

        engine = AllocationCalculationEngine()
        # We can get totals per account from engine
        alloc_res = engine.calculate_allocations(holdings_df)
        alloc_res.get("by_account", pd.DataFrame())

        # Map account_id (from index? no, index is account name. We need ID).
        # to_dataframe() uses: (Account_Type, Account_Category, Account_Name) as Index.
        # It doesn't have ID in index!
        # This is a limitation. We can map by Name if unique? Or verify if to_dataframe includes ID.
        # Account.to_dataframe sets index names.

        # Fallback to ORM sums if DF index is ambiguous.
        # ORM is safer for sidebar IDs.

        account_totals = {}
        grand_total = Decimal(0)

        for acc in accounts:
            val = acc.total_value() # This hits DB/Holdings
            account_totals[acc.id] = val
            grand_total += val

        # Groups
        all_groups = AccountGroup.objects.all().order_by('sort_order', 'name')
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for g in all_groups:
            groups[g.name] = {"label": g.name, "total": Decimal("0.00"), "accounts": []}

        if "Other" not in groups:
            groups["Other"] = {"label": "Other", "total": Decimal("0.00"), "accounts": []}

        for account in accounts:
            account_total = account_totals.get(account.id, Decimal(0))

            group_name = "Other"
            if account.account_type and account.account_type.group:
                group_name = account.account_type.group.name

            if group_name not in groups:
                group_name = "Other"

            groups[group_name]["accounts"].append(
                {
                    "id": account.id,
                    "name": account.name,
                    "institution": account.institution.name if account.institution else "N/A",
                    "total": account_total,
                    "absolute_deviation_pct": Decimal(0), # Placeholder for now
                }
            )
            groups[group_name]["total"] += account_total

        # Clean up empty groups
        keys_to_remove = [k for k, v in groups.items() if not v["accounts"]]
        for k in keys_to_remove:
            del groups[k]

        return {
            "sidebar_data": {
                "grand_total": grand_total,
                "groups": groups
            }
        }

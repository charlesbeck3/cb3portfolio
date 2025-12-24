from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any

from django.http import HttpRequest

from portfolio.models import Account, AccountGroup


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

        from portfolio.services.allocation_calculations import AllocationCalculationEngine

        engine = AllocationCalculationEngine()
        drifts = engine.calculate_account_drifts(user)

        # Fetch accounts with necessary relationships
        accounts = (
            Account.objects.filter(user=user)
            .select_related("account_type__group", "institution")
            .prefetch_related("holdings")
        )

        # Calculate account totals using prefetched holdings
        account_totals = {}
        grand_total = Decimal(0)

        for acc in accounts:
            val = acc.total_value()
            account_totals[acc.id] = val
            grand_total += val

        # Build groups structure
        all_groups = AccountGroup.objects.all().order_by("sort_order", "name")
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for g in all_groups:
            groups[g.name] = {"label": g.name, "total": Decimal("0.00"), "accounts": []}

        # Add "Other" group for ungrouped accounts
        if "Other" not in groups:
            groups["Other"] = {"label": "Other", "total": Decimal("0.00"), "accounts": []}

        # Populate groups with accounts
        for account in accounts:
            account_total = account_totals.get(account.id, Decimal(0))

            # Determine group
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
                    "absolute_deviation_pct": Decimal(str(drifts.get(account.id, 0.0))),
                }
            )
            groups[group_name]["total"] += account_total

        # Remove empty groups
        groups = OrderedDict((k, v) for k, v in groups.items() if v["accounts"])

        return {"sidebar_data": {"grand_total": grand_total, "groups": groups}}

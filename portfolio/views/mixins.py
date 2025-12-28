import logging
from collections import OrderedDict
from decimal import Decimal
from typing import Any

from django.http import HttpRequest

from portfolio.models import Account, AccountGroup

logger = logging.getLogger(__name__)


class PortfolioContextMixin:
    """Provides common portfolio context data for portfolio views."""

    request: HttpRequest

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Insert sidebar data into context."""
        context = super().get_context_data(**kwargs)  # type: ignore
        context.update(self.get_sidebar_context())
        return context

    def get_sidebar_context(self) -> dict[str, Any]:
        """
        Get sidebar data for all portfolio views.

        REFACTORED: Now uses AllocationCalculationEngine for both drifts and totals,
        eliminating duplicate calculation logic and improving performance.

        Automatically updates prices from market data on each request.
        """
        user = self.request.user
        if not user.is_authenticated:
            # Should be unreachable for views using LoginRequiredMixin
            return {"sidebar_data": {"grand_total": Decimal("0.00"), "groups": {}}}

        from portfolio.services.allocation_calculations import AllocationCalculationEngine
        from portfolio.services.pricing import PricingService

        # Auto-update prices on each page load
        pricing_service = PricingService()
        try:
            pricing_service.update_holdings_prices(user)
        except Exception as e:
            # Log error but don't break the page if price fetch fails
            logger.warning(f"Failed to update prices for {user.username}: {e}")

        engine = AllocationCalculationEngine()

        # Get both variances and totals from engine (single data source)
        variances = engine.calculate_account_variances(user)
        account_totals = engine.get_account_totals(user)  # NEW: Use engine
        grand_total = sum(account_totals.values())

        # Fetch accounts with minimal relationships (no holdings prefetch needed!)
        # Holdings are already processed by the engine
        accounts = (
            Account.objects.filter(user=user)
            .select_related("account_type__group", "institution")
            .order_by("account_type__group__sort_order", "name")
        )

        # Build groups structure
        all_groups = AccountGroup.objects.all().order_by("sort_order", "name")
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for g in all_groups:
            groups[g.name] = {"label": g.name, "total": Decimal("0.00"), "accounts": []}

        # Add "Other" group for ungrouped accounts
        if "Other" not in groups:
            groups["Other"] = {"label": "Other", "total": Decimal("0.00"), "accounts": []}

        # Populate groups with accounts (no more acc.total_value() calls!)
        for account in accounts:
            # Get pre-calculated total from engine
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
                    "institution": (account.institution.name if account.institution else "N/A"),
                    "total": account_total,
                    "absolute_deviation_pct": Decimal(str(variances.get(account.id, 0.0))),
                }
            )
            groups[group_name]["total"] += account_total

        # Remove empty groups
        groups = OrderedDict((k, v) for k, v in groups.items() if v["accounts"])

        return {"sidebar_data": {"grand_total": grand_total, "groups": groups}}

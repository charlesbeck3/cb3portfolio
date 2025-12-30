from decimal import Decimal
from typing import Any

from django.http import HttpRequest

import structlog

logger = structlog.get_logger(__name__)


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

        REFACTORED: Now uses AllocationCalculationEngine.get_sidebar_data()
        for optimized data retrieval with minimal queries.

        Automatically updates prices from market data on each request.

        Returns:
            dict with 'sidebar_data' containing grand_total and groups
        """
        user = self.request.user
        if not user.is_authenticated:
            return {"sidebar_data": {"grand_total": Decimal("0.00"), "groups": {}}}

        from portfolio.services.allocation_calculations import AllocationCalculationEngine
        from portfolio.services.pricing import PricingService

        # Auto-update prices on each page load if they are stale (>5 mins)
        pricing_service = PricingService()
        try:
            result = pricing_service.update_holdings_prices_if_stale(user)

            # Log results for monitoring
            if result["updated_count"] > 0:
                logger.info(
                    "prices_refreshed",
                    user_id=user.id,
                    updated=result["updated_count"],
                    skipped=result["skipped_count"],
                )

            if result["errors"]:
                logger.warning(
                    "price_update_errors", user_id=user.id, failed_tickers=result["errors"]
                )
        except Exception as e:
            # Log error but don't break the page if price fetch fails
            logger.error("price_service_error", user_id=user.id, error=str(e))

        engine = AllocationCalculationEngine()

        # OPTIMIZED: Single consolidated call for all sidebar data
        sidebar_data = engine.get_sidebar_data(user)

        # Log query count for monitoring (helps identify regressions)
        if sidebar_data["query_count"] > 10:
            logger.warning(
                "high_sidebar_query_count", user_id=user.id, queries=sidebar_data["query_count"]
            )

        # Format for template
        return {
            "sidebar_data": {
                "grand_total": sidebar_data["grand_total"],
                "groups": sidebar_data["accounts_by_group"],
            }
        }

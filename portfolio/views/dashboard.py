from typing import Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

import structlog

from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.services.allocation_presentation import AllocationPresentationFormatter
from portfolio.views.mixins import PortfolioContextMixin

logger = structlog.get_logger(__name__)


class DashboardView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        logger.info("dashboard_accessed", user_id=cast(Any, self.request.user).id)
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated:
            return context  # Should be unreachable due to LoginRequiredMixin

        # Initialize engine and formatter
        engine = AllocationCalculationEngine()
        formatter = AllocationPresentationFormatter()

        # Step 1: Build numeric DataFrame
        df = engine.build_presentation_dataframe(user=user)

        if not df.empty:
            # Step 2: Aggregate at all levels
            aggregated = engine.aggregate_presentation_levels(df)

            # Step 3: Format for display
            # Get metadata for formatting
            _, accounts_by_type = engine._get_account_metadata(user)
            strategies = engine._get_target_strategies(user)

            allocation_rows = formatter.format_presentation_rows(
                aggregated_data=aggregated,
                accounts_by_type=accounts_by_type,
                target_strategies=strategies,
            )
            # Pass same raw data to both, template will handle formatting based on mode
            context["allocation_rows_money"] = allocation_rows
            context["allocation_rows_percent"] = allocation_rows

            # Extract account types for column structure (required by index.html)
            if allocation_rows:
                context["account_types"] = allocation_rows[0].get("account_types", [])
        else:
            context["allocation_rows_money"] = []
            context["allocation_rows_percent"] = []

        return context

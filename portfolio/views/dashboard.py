from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.services.allocation_presentation import AllocationPresentationFormatter
from portfolio.views.mixins import PortfolioContextMixin


class DashboardView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        assert user.is_authenticated

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

            context["allocation_rows_money"] = formatter.format_presentation_rows(
                aggregated_data=aggregated,
                accounts_by_type=accounts_by_type,
                target_strategies=strategies,
                mode="dollar",
            )
            context["allocation_rows_percent"] = formatter.format_presentation_rows(
                aggregated_data=aggregated,
                accounts_by_type=accounts_by_type,
                target_strategies=strategies,
                mode="percent",
            )
        else:
            context["allocation_rows_money"] = []
            context["allocation_rows_percent"] = []

        return context

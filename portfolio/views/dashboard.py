from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.views.mixins import PortfolioContextMixin


class DashboardView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        assert user.is_authenticated

        # Initialize engine
        engine = AllocationCalculationEngine()

        # Get allocation rows using new engine method
        # Engine handles all data fetching, calculations, and row building internally
        context["allocation_rows_money"] = engine.get_target_allocation_presentation(
            user=user,
            mode="dollar"
        )
        context["allocation_rows_percent"] = engine.get_target_allocation_presentation(
            user=user,
            mode="percent"
        )

        return context

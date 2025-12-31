from typing import Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

import structlog

from portfolio.services.allocations import get_presentation_rows
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

        # Single clean API call using new allocations module
        allocation_rows = get_presentation_rows(user=user)

        # Template handles money vs percent formatting
        context["allocation_rows_money"] = allocation_rows
        context["allocation_rows_percent"] = allocation_rows

        # Extract account types for column structure (required by index.html)
        if allocation_rows:
            context["account_types"] = allocation_rows[0].get("account_types", [])

        return context

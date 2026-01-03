"""Views for portfolio rebalancing functionality."""

import csv
import logging
from io import StringIO
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.views.generic import TemplateView

from portfolio.services.rebalancing import RebalancingEngine
from portfolio.views.mixins import AccountOwnershipMixin, PortfolioContextMixin

logger = logging.getLogger(__name__)


class RebalancingView(
    LoginRequiredMixin, AccountOwnershipMixin, PortfolioContextMixin, TemplateView
):
    """Display rebalancing recommendations for an account."""

    template_name = "portfolio/rebalancing.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Handle GET requests with validation."""
        if not self.validate_account_ownership():
            return self.get_redirect_response()

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add rebalancing plan to context."""
        context = super().get_context_data(**kwargs)

        # Account already validated and loaded by mixin
        account = self.get_validated_account()

        # Generate rebalancing plan
        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        context["account"] = account
        context["plan"] = plan

        # Get target allocations for display
        strategy = account.get_effective_allocation_strategy()
        if strategy:
            context["target_allocations"] = {
                ta.asset_class: ta.target_percent
                for ta in strategy.target_allocations.select_related("asset_class")
            }
        else:
            context["target_allocations"] = {}

        # Add sidebar context
        context.update(self.get_sidebar_context())

        return context


class RebalancingExportView(LoginRequiredMixin, AccountOwnershipMixin, TemplateView):
    """Export rebalancing orders as CSV."""

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Generate and return CSV file."""
        if not self.validate_account_ownership():
            return self.get_redirect_response()

        # Account already validated and loaded by mixin
        account = self.get_validated_account()

        # Generate rebalancing plan
        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        # Create CSV
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "Action",
                "Ticker",
                "Security Name",
                "Asset Class",
                "Shares",
                "Price",
                "Estimated Amount",
            ]
        )

        # Orders
        for order in plan.orders:
            writer.writerow(
                [
                    order.action,
                    order.security.ticker,
                    order.security.name,
                    order.asset_class.name,
                    order.shares,
                    f"{order.price_per_share:.2f}",
                    f"{order.estimated_amount:.2f}",
                ]
            )

        # Create response
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        filename = f"rebalancing_{account.name.replace(' ', '_')}_{plan.generated_at:%Y%m%d}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response

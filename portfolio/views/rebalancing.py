"""Views for portfolio rebalancing functionality."""

import csv
import logging
from io import StringIO
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView

from portfolio.models import Account
from portfolio.services.rebalancing import RebalancingEngine
from portfolio.utils.security import (
    AccessControlError,
    InvalidInputError,
    sanitize_integer_input,
    validate_user_owns_account,
)
from portfolio.views.mixins import PortfolioContextMixin

logger = logging.getLogger(__name__)


class RebalancingView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    """Display rebalancing recommendations for an account."""

    template_name = "portfolio/rebalancing.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Handle GET requests with validation."""
        user = request.user

        # SECURITY: Validate account_id
        account_id_raw = kwargs.get("account_id")
        try:
            account_id = sanitize_integer_input(account_id_raw, "account_id", min_val=1)
            validate_user_owns_account(user, account_id)
        except (InvalidInputError, AccessControlError) as e:
            logger.warning(
                "Account validation failed: user=%s, account_id=%s, error=%s",
                user.id,
                account_id_raw,
                str(e),
            )
            messages.error(request, str(e))
            return redirect("portfolio:holdings")

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add rebalancing plan to context."""
        context = super().get_context_data(**kwargs)

        account_id = kwargs.get("account_id")
        account = Account.objects.select_related(
            "account_type", "portfolio", "allocation_strategy"
        ).get(id=account_id)

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


class RebalancingExportView(LoginRequiredMixin, TemplateView):
    """Export rebalancing orders as CSV."""

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Generate and return CSV file."""
        user = request.user
        account_id_raw = kwargs.get("account_id")

        # SECURITY: Validate account_id
        try:
            account_id = sanitize_integer_input(account_id_raw, "account_id", min_val=1)
            account = validate_user_owns_account(user, account_id)
        except (InvalidInputError, AccessControlError) as e:
            logger.warning(
                "Export validation failed: user=%s, account_id=%s, error=%s",
                user.id,
                account_id_raw,
                str(e),
            )
            messages.error(request, str(e))
            return redirect("portfolio:holdings")

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

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.views.generic import TemplateView

import structlog

from portfolio.models import (
    Account,
    AccountType,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
)
from portfolio.views.mixins import PortfolioContextMixin

logger = structlog.get_logger(__name__)


class TargetAllocationView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    """
    View for managing target allocations and strategy assignments.

    Handles:
    - Display of current allocations vs targets
    - Assignment of strategies to account types
    - Override strategies for individual accounts
    """

    template_name = "portfolio/target_allocations.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Build context using new allocations module."""
        from decimal import Decimal

        from portfolio.services.allocations import get_presentation_rows

        logger.info("target_allocations_accessed", user_id=cast(Any, self.request.user).id)
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_authenticated:
            return context

        user = cast(Any, user)

        # Get presentation rows using new engine (already sorted by effective desc)
        allocation_rows = get_presentation_rows(user=user)

        # Extract portfolio total from grand total row
        portfolio_total = Decimal("0.00")
        if allocation_rows:
            # hierarchy_level -1 is grand total
            grand_total_row = next(
                (r for r in allocation_rows if r.get("hierarchy_level") == -1), None
            )
            if grand_total_row and "portfolio" in grand_total_row:
                portfolio_total = Decimal(str(grand_total_row["portfolio"]["actual"]))

        # Get user's strategies
        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        context.update(
            {
                "allocation_rows_percent": allocation_rows,
                "allocation_rows_money": allocation_rows,
                "strategies": strategies,
                "portfolio_total_value": portfolio_total,
            }
        )
        return context

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Handle POST request to save strategy assignments.

        Processes two types of assignments:
        1. Account type level: strategy_at_{type_id}
        2. Individual account overrides: strategy_acc_{account_id}

        Empty string values clear the assignment.
        """
        user = request.user
        if not user.is_authenticated:
            messages.error(request, "Authentication required.")
            return redirect("portfolio:target_allocations")

        user = cast(Any, user)

        try:
            # Get user's account types and accounts
            account_types = AccountType.objects.filter(accounts__user=user).distinct()
            accounts = Account.objects.filter(user=user)

            with transaction.atomic():
                # 1. Process account type assignments
                for account_type in account_types:
                    key = f"strategy_at_{account_type.id}"
                    strategy_id = request.POST.get(key, "").strip()

                    if strategy_id == "":
                        # Empty string = remove assignment
                        AccountTypeStrategyAssignment.objects.filter(
                            user=user, account_type=account_type
                        ).delete()
                    elif strategy_id:
                        # Validate strategy belongs to user
                        try:
                            strategy = AllocationStrategy.objects.get(id=strategy_id, user=user)
                            AccountTypeStrategyAssignment.objects.update_or_create(
                                user=user,
                                account_type=account_type,
                                defaults={"allocation_strategy": strategy},
                            )
                        except AllocationStrategy.DoesNotExist:
                            # Invalid strategy ID - log but continue
                            logger.warning(
                                "invalid_strategy_id_in_post",
                                user_id=user.id,
                                strategy_id=strategy_id,
                                key=key,
                            )

                # 2. Process individual account overrides
                for account in accounts:
                    key = f"strategy_acc_{account.id}"
                    strategy_id = request.POST.get(key, "").strip()

                    if strategy_id == "":
                        # Empty string = clear override
                        account.allocation_strategy = None
                        account.save(update_fields=["allocation_strategy"])
                    elif strategy_id:
                        # Validate strategy belongs to user
                        try:
                            strategy = AllocationStrategy.objects.get(id=strategy_id, user=user)
                            account.allocation_strategy = strategy
                            account.save(update_fields=["allocation_strategy"])
                        except AllocationStrategy.DoesNotExist:
                            # Invalid strategy ID - log but continue
                            logger.warning(
                                "invalid_strategy_id_in_post",
                                user_id=user.id,
                                strategy_id=strategy_id,
                                key=key,
                            )

            messages.success(request, "Allocations updated.")
            return redirect("portfolio:target_allocations")

        except Exception as e:
            logger.error(
                "error_saving_allocations",
                user_id=user.id,
                error=str(e),
                exc_info=True,
            )
            messages.error(request, "Error saving allocations. Please try again.")
            return redirect("portfolio:target_allocations")

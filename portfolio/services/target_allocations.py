from decimal import Decimal
from typing import Any, cast

from django.db import transaction

import structlog

from portfolio.models import (
    Account,
    AccountType,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from users.models import CustomUser

logger = structlog.get_logger(__name__)


class TargetAllocationViewService:
    def build_context(self, *, user: CustomUser) -> dict[str, Any]:
        logger.info("building_target_allocation_context", user_id=cast(Any, user).id)
        engine = AllocationCalculationEngine()

        # Single clean API call
        allocation_rows = engine.get_presentation_rows(user=user)

        portfolio_total = Decimal("0.00")
        if allocation_rows:
            # Find grand total row to extract total portfolio value
            # It should be the last row, but search explicitly to be safe
            grand_total_row = next((r for r in allocation_rows if r.get("is_grand_total")), None)
            if grand_total_row and "portfolio" in grand_total_row:
                portfolio_total = Decimal(str(grand_total_row["portfolio"]["actual"]))

        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        return {
            "allocation_rows_percent": allocation_rows,
            "allocation_rows_money": allocation_rows,
            # Pass same rows, template handles formatting
            "strategies": strategies,
            "portfolio_total_value": portfolio_total,
        }

        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        return {
            "allocation_rows_percent": allocation_rows,
            "allocation_rows_money": allocation_rows,
            "strategies": strategies,
            "portfolio_total_value": portfolio_total,
        }

    def save_from_post(self, *, request: Any) -> tuple[bool, list[str]]:
        user = request.user
        if not user.is_authenticated:
            return False, ["Authentication required."]

        user = cast(Any, user)

        account_types = AccountType.objects.filter(accounts__user=user).distinct()
        accounts = Account.objects.filter(user=user)

        with transaction.atomic():
            # 1. Update Account Type Strategies
            for at in account_types:
                strategy_id_str = request.POST.get(f"strategy_at_{at.id}")

                # If "Select Strategy" (empty string) is chosen, we remove the assignment
                if not strategy_id_str:
                    AccountTypeStrategyAssignment.objects.filter(
                        user=user, account_type=at
                    ).delete()
                    continue

                try:
                    strategy_id = int(strategy_id_str)
                    strategy = AllocationStrategy.objects.get(id=strategy_id, user=user)

                    AccountTypeStrategyAssignment.objects.update_or_create(
                        user=user,
                        account_type=at,
                        defaults={"allocation_strategy": strategy},
                    )
                except (ValueError, AllocationStrategy.DoesNotExist):
                    # Invalid input or strategy doesn't exist/belong to user
                    pass

            # 2. Update Account Overrides
            for acc in accounts:
                strategy_id_str = request.POST.get(f"strategy_acc_{acc.id}")

                if not strategy_id_str:
                    if acc.allocation_strategy:
                        acc.allocation_strategy = None
                        acc.save(update_fields=["allocation_strategy"])
                    continue

                try:
                    strategy_id = int(strategy_id_str)
                    strategy = AllocationStrategy.objects.get(id=strategy_id, user=user)

                    if acc.allocation_strategy_id != strategy.id:
                        acc.allocation_strategy = strategy
                        acc.save(update_fields=["allocation_strategy"])
                except (ValueError, AllocationStrategy.DoesNotExist):
                    pass

        return True, []

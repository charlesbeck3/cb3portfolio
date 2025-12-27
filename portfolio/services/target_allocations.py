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
from portfolio.services.allocation_presentation import AllocationPresentationFormatter
from users.models import CustomUser

logger = structlog.get_logger(__name__)


class TargetAllocationViewService:
    def build_context(self, *, user: CustomUser) -> dict[str, Any]:
        logger.info("building_target_allocation_context", user_id=cast(Any, user).id)
        engine = AllocationCalculationEngine()
        formatter = AllocationPresentationFormatter()

        # Step 1: Build numeric DataFrame
        df = engine.build_presentation_dataframe(user=user)

        allocation_rows_percent = []
        allocation_rows_money = []
        portfolio_total = Decimal("0.00")

        if not df.empty:
            # Step 2: Aggregate at all levels
            aggregated = engine.aggregate_presentation_levels(df)

            # Step 3: Format for display
            # Get metadata for formatting
            _, accounts_by_type = engine._get_account_metadata(user)
            strategies_data = engine._get_target_strategies(user)

            allocation_rows_percent = formatter.format_presentation_rows(
                aggregated_data=aggregated,
                accounts_by_type=accounts_by_type,
                target_strategies=strategies_data,
                mode="percent",
            )
            allocation_rows_money = formatter.format_presentation_rows(
                aggregated_data=aggregated,
                accounts_by_type=accounts_by_type,
                target_strategies=strategies_data,
                mode="dollar",
            )

            # Calculate portfolio total for display
            portfolio_total = Decimal(float(aggregated["grand_total"].iloc[0]["portfolio_actual"]))

        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        return {
            "allocation_rows_percent": allocation_rows_percent,
            "allocation_rows_money": allocation_rows_money,
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

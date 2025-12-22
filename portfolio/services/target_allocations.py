from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from django.db import transaction

from portfolio.models import (
    Account,
    AccountType,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from users.models import CustomUser


class TargetAllocationViewService:
    def build_context(self, *, user: CustomUser) -> dict[str, Any]:
        engine = AllocationCalculationEngine()

        # Simple engine call (replaces ~150 lines of legacy code)
        allocation_rows_percent = engine.get_target_allocation_presentation(
            user=user,
            mode="percent"
        )
        allocation_rows_money = engine.get_target_allocation_presentation(
            user=user,
            mode="dollar"
        )

        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        # Calculate portfolio total for display
        from portfolio.models import Portfolio
        portfolio = Portfolio.objects.filter(user=user).first()
        portfolio_total = Decimal("0.00")
        if portfolio:
            holdings_df = portfolio.to_dataframe()
            if not holdings_df.empty:
                # holdings_df values are individual security dollars
                portfolio_total = Decimal(float(holdings_df.sum().sum()))

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

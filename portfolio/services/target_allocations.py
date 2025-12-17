from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from django.db import transaction

from portfolio.models import (
    Account,
    AccountType,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    AssetClass,
    Holding,
    TargetAllocation,
)
from portfolio.presenters import TargetAllocationTableBuilder
from users.models import CustomUser


class TargetAllocationViewService:
    def build_context(self, *, user: CustomUser, summary_service: Any) -> dict[str, Any]:
        defaults_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        overrides_map: dict[int, dict[int, Decimal]] = defaultdict(dict)

        account_types_qs = (
            AccountType.objects.filter(accounts__user=user)
            .distinct()
            .order_by("group__sort_order", "label")
        )

        assignments = (
            AccountTypeStrategyAssignment.objects.filter(
                user=user, account_type__in=account_types_qs
            )
            .select_related("account_type", "allocation_strategy")
            .all()
        )
        assignment_by_at_id = {a.account_type_id: a for a in assignments}

        strategy_ids: set[int] = {a.allocation_strategy_id for a in assignments}

        accounts = (
            Account.objects.filter(user=user)
            .select_related("account_type", "allocation_strategy")
            .all()
        )
        account_map = {a.id: a for a in accounts}

        override_accounts = [a for a in accounts if a.allocation_strategy_id]
        strategy_ids.update(cast(int, a.allocation_strategy_id) for a in override_accounts)

        strategy_allocations = (
            TargetAllocation.objects.filter(strategy_id__in=strategy_ids)
            .select_related("asset_class")
            .all()
        )

        alloc_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        for alloc in strategy_allocations:
            alloc_map[alloc.strategy_id][alloc.asset_class_id] = alloc.target_percent

        for at_id, assignment in assignment_by_at_id.items():
            defaults_map[at_id] = alloc_map.get(assignment.allocation_strategy_id, {})

        for acc in override_accounts:
            overrides_map[acc.id] = alloc_map.get(cast(int, acc.allocation_strategy_id), {})

        summary = summary_service.get_holdings_summary(user)

        sidebar_data = summary_service.get_account_summary(user)

        account_totals: dict[int, Decimal] = {}
        for group in sidebar_data["groups"].values():
            for acc in group["accounts"]:
                account_totals[acc["id"]] = acc["total"]

        at_totals = summary.account_type_grand_totals

        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        at_values: dict[int, Decimal] = {}
        account_types: list[Any] = []

        for at_obj in account_types_qs:
            at: Any = at_obj
            at_accounts = [a for a in accounts if a.account_type_id == at.id]

            at.current_total_value = at_totals.get(at.code, Decimal("0.00"))
            at.target_map = defaults_map.get(at.id, {})
            at_values[at.id] = at.current_total_value

            for acc in at_accounts:
                acc.current_total_value = account_totals.get(acc.id, Decimal("0.00"))  # type: ignore[attr-defined]
                acc.target_map = overrides_map.get(acc.id, {})  # type: ignore[attr-defined]

            if at.id in assignment_by_at_id:
                at.active_strategy_id = assignment_by_at_id[at.id].allocation_strategy_id
            else:
                at.active_strategy_id = None

            at.active_accounts = at_accounts
            account_types.append(at)

        holdings = (
            Holding.objects.filter(account__user=user)
            .select_related("security", "account")
            .only("account_id", "security__asset_class_id", "shares", "current_price")
        )

        account_ac_map: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        at_ac_map: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

        for h in holdings:
            if h.current_price:
                val = h.shares * h.current_price
                if val > 0:
                    ac_id = h.security.asset_class_id
                    acc_id = h.account.id
                    at_id = account_map[acc_id].account_type_id

                    account_ac_map[acc_id][ac_id] += val
                    at_ac_map[at_id][ac_id] += val

        ac_id_to_cat: dict[int, str] = {}
        for group in summary.groups.values():
            for cat_code, cat_data in group.categories.items():
                for _ac_name, ac_data in cat_data.asset_classes.items():
                    if ac_data.id:
                        ac_id_to_cat[ac_data.id] = cat_code

        for at in account_types:
            at.dollar_map = at_ac_map[at.id]
            at.allocation_map = {}
            if at.current_total_value > 0:
                for ac_id, val in at.dollar_map.items():
                    at.allocation_map[ac_id] = (val / at.current_total_value) * 100

            for acc in at.active_accounts:
                acc.dollar_map = account_ac_map[acc.id]
                acc.allocation_map = {}
                if acc.current_total_value > 0:
                    for ac_id, val in acc.dollar_map.items():
                        acc.allocation_map[ac_id] = (val / acc.current_total_value) * 100

                acc.category_map = defaultdict(Decimal)
                for ac_id, val in acc.dollar_map.items():
                    holding_cat_code = ac_id_to_cat.get(ac_id)
                    if holding_cat_code:
                        acc.category_map[holding_cat_code] += val

        cash_ac = AssetClass.objects.filter(name="Cash").first()

        builder = TargetAllocationTableBuilder()
        allocation_rows_percent = builder.build_rows(
            summary=summary,
            account_types=account_types,
            portfolio_total_value=summary.grand_total,
            mode="percent",
            cash_asset_class_id=cash_ac.id if cash_ac else None,
        )
        allocation_rows_money = builder.build_rows(
            summary=summary,
            account_types=account_types,
            portfolio_total_value=summary.grand_total,
            mode="dollar",
            cash_asset_class_id=cash_ac.id if cash_ac else None,
        )

        return {
            "summary": summary,
            "sidebar_data": sidebar_data,
            "account_types": account_types,
            "portfolio_total_value": summary.grand_total,
            "allocation_rows_percent": allocation_rows_percent,
            "allocation_rows_money": allocation_rows_money,
            "at_values": at_values,
            "account_totals": account_totals,
            "defaults_map": defaults_map,
            "cash_asset_class_id": cash_ac.id if cash_ac else None,
            "strategies": strategies,
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

from __future__ import annotations

import contextlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from django.db import transaction

from portfolio.forms import TargetAllocationForm
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
            AccountTypeStrategyAssignment.objects.filter(user=user, account_type__in=account_types_qs)
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
        }

    def save_from_post(self, *, request: Any) -> tuple[bool, list[str]]:
        user = request.user
        if not user.is_authenticated:
            return False, ["Authentication required."]

        user = cast(Any, user)

        account_types = AccountType.objects.filter(accounts__user=user).distinct()

        try:
            cash_ac = AssetClass.objects.get(name="Cash")
        except AssetClass.DoesNotExist:
            return False, ["Cash asset class not found."]

        input_asset_classes = list(AssetClass.objects.exclude(name="Cash").all())

        form = TargetAllocationForm(
            request.POST or None,
            account_types=account_types,
            asset_classes=input_asset_classes,
        )

        if not form.is_valid():
            form_errors: list[str] = []
            for field, field_errors in form.errors.items():
                for err in field_errors:
                    form_errors.append(f"{field}: {err}")
            return False, form_errors

        default_updates: dict[int, dict[int, Decimal]] = defaultdict(dict)
        override_updates: dict[int, dict[int, Decimal]] = defaultdict(dict)

        errors: list[str] = []

        parsed_defaults = form.get_parsed_targets()

        for at in account_types:
            total_pct = Decimal("0.00")
            at_defaults = parsed_defaults.get(at.id, {})

            for ac in input_asset_classes:
                val = at_defaults.get(ac.id, Decimal("0.00"))
                if val < 0:
                    errors.append(f"Negative allocation for {at.label}")
                default_updates[at.id][ac.id] = val
                total_pct += val

            cash_residual = Decimal("100.00") - total_pct
            if cash_residual < 0:
                if cash_residual < Decimal("-0.01"):
                    errors.append(f"Total allocation for {at.label} exceeds 100% ({total_pct}%)")
                cash_residual = Decimal("0.00")

            default_updates[at.id][cash_ac.id] = cash_residual

        accounts = Account.objects.filter(user=user)

        for acc in accounts:
            has_explicit_input = False

            for ac in input_asset_classes:
                input_key = f"target_account_{acc.id}_{ac.id}"
                val_str = request.POST.get(input_key, "").strip()
                if val_str:
                    has_explicit_input = True
                    break

            if not has_explicit_input:
                cash_input_key = f"target_account_{acc.id}_{cash_ac.id}"
                if request.POST.get(cash_input_key, "").strip():
                    has_explicit_input = True

            if has_explicit_input:
                effective_values: dict[int, Decimal] = {}

                for ac in input_asset_classes:
                    input_key = f"target_account_{acc.id}_{ac.id}"
                    val_str = request.POST.get(input_key, "").strip()

                    if val_str:
                        try:
                            val = Decimal(val_str)
                            override_updates[acc.id][ac.id] = val
                            effective_values[ac.id] = val
                        except ValueError:
                            errors.append(f"Invalid value for {acc.name} - {ac.name}")
                    else:
                        effective_values[ac.id] = Decimal("0.00")

                cash_input_key = f"target_account_{acc.id}_{cash_ac.id}"
                cash_val_str = request.POST.get(cash_input_key, "").strip()

                total_standard = sum(effective_values.values(), Decimal("0.00"))

                if cash_val_str:
                    try:
                        cash_val = Decimal(cash_val_str)
                        override_updates[acc.id][cash_ac.id] = cash_val
                    except ValueError:
                        errors.append(f"Invalid value for {acc.name} - Cash")
                else:
                    cash_residual = Decimal("100.00") - total_standard
                    override_updates[acc.id][cash_ac.id] = max(Decimal("0.00"), cash_residual)

        if errors:
            return False, errors

        try:
            with transaction.atomic():
                account_types_by_id = {at.id: at for at in account_types}

                for at_id, ac_map in default_updates.items():
                    at = account_types_by_id.get(at_id)
                    if at is None:
                        continue

                    strategy, _ = AllocationStrategy.objects.update_or_create(
                        user=user,
                        name=f"{at.label} Strategy",
                        defaults={"description": f"Default strategy for {at.label}"},
                    )

                    strategy.target_allocations.all().delete()
                    TargetAllocation.objects.bulk_create(
                        [
                            TargetAllocation(
                                strategy=strategy,
                                asset_class_id=ac_id,
                                target_percent=val,
                            )
                            for ac_id, val in ac_map.items()
                        ]
                    )

                    AccountTypeStrategyAssignment.objects.update_or_create(
                        user=user,
                        account_type=at,
                        defaults={"allocation_strategy": strategy},
                    )

                accounts_by_id = {a.id: a for a in accounts}
                for acc in accounts:
                    if acc.id in override_updates:
                        strategy, _ = AllocationStrategy.objects.update_or_create(
                            user=user,
                            name=f"{acc.name} Strategy",
                            defaults={"description": f"Account override strategy for {acc.name}"},
                        )

                        strategy.target_allocations.all().delete()
                        TargetAllocation.objects.bulk_create(
                            [
                                TargetAllocation(
                                    strategy=strategy,
                                    asset_class_id=ac_id,
                                    target_percent=val,
                                )
                                for ac_id, val in override_updates[acc.id].items()
                            ]
                        )

                        if acc.allocation_strategy_id != strategy.id:
                            acc.allocation_strategy = strategy
                            acc.save(update_fields=["allocation_strategy"])
                    else:
                        if acc.allocation_strategy_id:
                            acc.allocation_strategy = None
                            acc.save(update_fields=["allocation_strategy"])

                _ = accounts_by_id

            return True, []
        except Exception as e:  # pragma: no cover
            return False, [f"Error saving targets: {e}"]

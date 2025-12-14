from __future__ import annotations

import contextlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from django.db import transaction

from portfolio.forms import TargetAllocationForm
from portfolio.models import Account, AccountType, AssetClass, Holding, TargetAllocation
from portfolio.presenters import TargetAllocationTableBuilder
from users.models import CustomUser


class TargetAllocationViewService:
    def build_context(self, *, user: CustomUser, summary_service: Any) -> dict[str, Any]:
        targets = TargetAllocation.objects.filter(user=user).select_related(
            "account_type", "asset_class", "account"
        )

        defaults_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        overrides_map: dict[int, dict[int, Decimal]] = defaultdict(dict)

        for t in targets:
            if t.account_id:
                overrides_map[t.account_id][t.asset_class_id] = t.target_pct
            else:
                defaults_map[t.account_type_id][t.asset_class_id] = t.target_pct

        summary = summary_service.get_holdings_summary(user)

        account_types_qs = (
            AccountType.objects.filter(accounts__user=user)
            .distinct()
            .order_by("group__sort_order", "label")
        )

        accounts = Account.objects.filter(user=user).select_related("account_type")
        account_map = {a.id: a for a in accounts}

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
                current_defaults = TargetAllocation.objects.filter(user=user, account__isnull=True)
                default_map_obj = {(t.account_type_id, t.asset_class_id): t for t in current_defaults}

                for at_id, ac_map in default_updates.items():
                    for ac_id, val in ac_map.items():
                        lookup = (at_id, ac_id)
                        if lookup in default_map_obj:
                            obj = default_map_obj[lookup]
                            if obj.target_pct != val:
                                obj.target_pct = val
                                obj.save()
                            del default_map_obj[lookup]
                        else:
                            TargetAllocation.objects.create(
                                user=user,
                                account_type_id=at_id,
                                asset_class_id=ac_id,
                                target_pct=val,
                            )

                current_overrides = TargetAllocation.objects.filter(user=user, account__isnull=False)
                override_obj_map = {
                    (cast(int, t.account_id), t.asset_class_id): t for t in current_overrides
                }

                processed_overrides: set[tuple[int, int]] = set()

                for acc_id, ac_map in override_updates.items():
                    for ac_id, val in ac_map.items():
                        lookup = (acc_id, ac_id)
                        processed_overrides.add(lookup)

                        if lookup in override_obj_map:
                            obj = override_obj_map[lookup]
                            if obj.target_pct != val:
                                obj.target_pct = val
                                obj.save()
                        else:
                            with contextlib.suppress(Account.DoesNotExist):
                                TargetAllocation.objects.create(
                                    user=user,
                                    account_type_id=Account.objects.get(id=acc_id).account_type_id,
                                    account_id=acc_id,
                                    asset_class_id=ac_id,
                                    target_pct=val,
                                )

                for lookup, obj in override_obj_map.items():
                    if lookup not in processed_overrides:
                        obj.delete()

            return True, []
        except Exception as e:  # pragma: no cover
            return False, [f"Error saving targets: {e}"]

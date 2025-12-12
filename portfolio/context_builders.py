from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from portfolio.templatetags.portfolio_extras import (
    accounting_amount,
    accounting_percent,
    percentage_of,
)


@dataclass(frozen=True)
class AccountTypeColumnData:
    code: str
    label: str
    current: str
    target: str
    variance: str
    current_raw: Decimal
    target_raw: Decimal
    variance_raw: Decimal


@dataclass(frozen=True)
class AllocationTableRow:
    asset_class_id: int
    asset_class_name: str
    category_code: str
    is_subtotal: bool
    is_group_total: bool
    is_grand_total: bool
    is_cash: bool
    account_type_data: list[AccountTypeColumnData]
    portfolio_current: str
    portfolio_target: str
    portfolio_variance: str


class AllocationTableBuilder:
    def build_rows(
        self,
        *,
        summary: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        cash_asset_class_id: int | None,
    ) -> list[AllocationTableRow]:
        rows: list[AllocationTableRow] = []

        category_labels = getattr(summary, "category_labels", {})
        group_labels = getattr(summary, "group_labels", {})

        effective_mode = "money" if mode == "dollar" else mode

        for group_code, group_data in summary.groups.items():
            for category_code, cat_data in group_data.categories.items():
                for ac_name, ac_data in cat_data.asset_classes.items():
                    if cash_asset_class_id is not None and ac_data.id == cash_asset_class_id:
                        continue

                    rows.append(
                        self._build_asset_row(
                            ac_name=ac_name,
                            ac_data=ac_data,
                            category_code=category_code,
                            account_types=account_types,
                            portfolio_total_value=portfolio_total_value,
                            mode=effective_mode,
                        )
                    )

                if len(cat_data.asset_classes) > 1:
                    category_label = category_labels.get(category_code, category_code)
                    rows.append(
                        self._build_category_subtotal_row(
                            category_code=category_code,
                            category_label=category_label,
                            cat_data=cat_data,
                            account_types=account_types,
                            portfolio_total_value=portfolio_total_value,
                            mode=effective_mode,
                        )
                    )

            if group_data.asset_class_count > 1 and len(group_data.categories) > 1:
                group_label = group_data.label or group_labels.get(group_code, group_code)
                rows.append(
                    self._build_group_total_row(
                        group_label=group_label,
                        group_data=group_data,
                        account_types=account_types,
                        portfolio_total_value=portfolio_total_value,
                        mode=effective_mode,
                    )
                )

        if cash_asset_class_id is not None:
            cash_group = summary.groups.get("CASH")
            if cash_group is not None:
                rows.append(
                    self._build_cash_row(
                        cash_asset_class_id=cash_asset_class_id,
                        cash_group=cash_group,
                        account_types=account_types,
                        portfolio_total_value=portfolio_total_value,
                        mode=effective_mode,
                    )
                )

        rows.append(
            self._build_grand_total_row(
                summary=summary,
                account_types=account_types,
                portfolio_total_value=portfolio_total_value,
                mode=effective_mode,
            )
        )

        return rows

    def _build_asset_row(
        self,
        *,
        ac_name: str,
        ac_data: Any,
        category_code: str,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> AllocationTableRow:
        at_columns: list[AccountTypeColumnData] = []

        for at in account_types:
            at_total_value = getattr(at, "current_total_value", Decimal("0.00"))
            at_summary = ac_data.account_types.get(at.code)
            current_val = (
                getattr(at_summary, "current", Decimal("0.00"))
                if at_summary is not None
                else Decimal("0.00")
            )
            target_val = (
                getattr(at_summary, "target", Decimal("0.00"))
                if at_summary is not None
                else Decimal("0.00")
            )
            configured_target_pct = at.target_map.get(ac_data.id, Decimal("0.00"))

            if mode == "percent":
                current_pct = (
                    percentage_of(current_val, at_total_value)
                    if at_total_value > 0
                    else Decimal("0.00")
                )
                target_pct = (
                    percentage_of(target_val, at_total_value)
                    if at_total_value > 0
                    else Decimal("0.00")
                )

                # If this account type has no value, or summary target dollars are missing/zero,
                # fall back to configured default targets.
                if at_total_value == 0 or (target_val == 0 and configured_target_pct > 0):
                    target_pct = configured_target_pct

                variance_pct = current_pct - target_pct

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_percent(current_pct, 1)),
                        target=str(accounting_percent(target_pct, 1)),
                        variance=str(accounting_percent(variance_pct, 1)),
                        current_raw=current_pct,
                        target_raw=target_pct,
                        variance_raw=variance_pct,
                    )
                )
            else:
                if target_val == 0 and configured_target_pct > 0:
                    target_val = at_total_value * (configured_target_pct / Decimal("100.00"))
                variance_val = current_val - target_val

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_amount(current_val, 0)),
                        target=str(accounting_amount(target_val, 0)) if target_val > 0 else "--",
                        variance=str(accounting_amount(variance_val, 0)),
                        current_raw=current_val,
                        target_raw=target_val,
                        variance_raw=variance_val,
                    )
                )

        if mode == "percent":
            portfolio_current_pct = (
                percentage_of(ac_data.total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_target_pct = (
                percentage_of(ac_data.target_total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_variance_pct = (
                percentage_of(ac_data.variance_total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )

            portfolio_current = str(accounting_percent(portfolio_current_pct, 1))
            portfolio_target = str(accounting_percent(portfolio_target_pct, 1))
            portfolio_variance = str(accounting_percent(portfolio_variance_pct, 1))
        else:
            portfolio_current = str(accounting_amount(ac_data.total, 0))
            portfolio_target = str(accounting_amount(ac_data.target_total, 0))
            portfolio_variance = str(accounting_amount(ac_data.variance_total, 0))

        return AllocationTableRow(
            asset_class_id=ac_data.id or 0,
            asset_class_name=ac_name,
            category_code=category_code,
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=False,
            is_cash=False,
            account_type_data=at_columns,
            portfolio_current=portfolio_current,
            portfolio_target=portfolio_target,
            portfolio_variance=portfolio_variance,
        )

    def _build_category_subtotal_row(
        self,
        *,
        category_code: str,
        category_label: str,
        cat_data: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> AllocationTableRow:
        at_columns: list[AccountTypeColumnData] = []

        for at in account_types:
            current_val = cat_data.account_type_totals.get(at.code, Decimal("0.00"))
            target_val = cat_data.account_type_target_totals.get(at.code, Decimal("0.00"))
            variance_pct = cat_data.account_type_variance_pct.get(at.code, Decimal("0.00"))

            if mode == "percent":
                current_pct = (
                    percentage_of(current_val, at.current_total_value)
                    if at.current_total_value > 0
                    else Decimal("0.00")
                )
                target_pct = (
                    percentage_of(target_val, at.current_total_value)
                    if at.current_total_value > 0
                    else Decimal("0.00")
                )

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_percent(current_pct, 1)),
                        target=str(accounting_percent(target_pct, 1)),
                        variance=str(accounting_percent(variance_pct, 1)),
                        current_raw=current_pct,
                        target_raw=target_pct,
                        variance_raw=variance_pct,
                    )
                )
            else:
                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_amount(current_val, 0)),
                        target=str(accounting_amount(target_val, 0)),
                        variance=str(accounting_amount(current_val - target_val, 0)),
                        current_raw=current_val,
                        target_raw=target_val,
                        variance_raw=current_val - target_val,
                    )
                )

        if mode == "percent":
            portfolio_current_pct = (
                percentage_of(cat_data.total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_target_pct = (
                percentage_of(cat_data.target_total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_variance_pct = (
                percentage_of(cat_data.variance_total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )

            portfolio_current = str(accounting_percent(portfolio_current_pct, 1))
            portfolio_target = str(accounting_percent(portfolio_target_pct, 1))
            portfolio_variance = str(accounting_percent(portfolio_variance_pct, 1))
        else:
            portfolio_current = str(accounting_amount(cat_data.total, 0))
            portfolio_target = str(accounting_amount(cat_data.target_total, 0))
            portfolio_variance = str(accounting_amount(cat_data.total - cat_data.target_total, 0))

        return AllocationTableRow(
            asset_class_id=0,
            asset_class_name=f"{category_label} Total",
            category_code=category_code,
            is_subtotal=True,
            is_group_total=False,
            is_grand_total=False,
            is_cash=False,
            account_type_data=at_columns,
            portfolio_current=portfolio_current,
            portfolio_target=portfolio_target,
            portfolio_variance=portfolio_variance,
        )

    def _build_group_total_row(
        self,
        *,
        group_label: str,
        group_data: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> AllocationTableRow:
        at_columns: list[AccountTypeColumnData] = []

        for at in account_types:
            current_val = group_data.account_type_totals.get(at.code, Decimal("0.00"))
            target_val = group_data.account_type_target_totals.get(at.code, Decimal("0.00"))
            variance_pct = group_data.account_type_variance_pct.get(at.code, Decimal("0.00"))

            if mode == "percent":
                current_pct = (
                    percentage_of(current_val, at.current_total_value)
                    if at.current_total_value > 0
                    else Decimal("0.00")
                )
                target_pct = (
                    percentage_of(target_val, at.current_total_value)
                    if at.current_total_value > 0
                    else Decimal("0.00")
                )

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_percent(current_pct, 1)),
                        target=str(accounting_percent(target_pct, 1)),
                        variance=str(accounting_percent(variance_pct, 1)),
                        current_raw=current_pct,
                        target_raw=target_pct,
                        variance_raw=variance_pct,
                    )
                )
            else:
                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_amount(current_val, 0)),
                        target=str(accounting_amount(target_val, 0)),
                        variance=str(accounting_amount(current_val - target_val, 0)),
                        current_raw=current_val,
                        target_raw=target_val,
                        variance_raw=current_val - target_val,
                    )
                )

        if mode == "percent":
            portfolio_current_pct = (
                percentage_of(group_data.total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_target_pct = (
                percentage_of(group_data.target_total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_variance_pct = (
                percentage_of(group_data.variance_total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )

            portfolio_current = str(accounting_percent(portfolio_current_pct, 1))
            portfolio_target = str(accounting_percent(portfolio_target_pct, 1))
            portfolio_variance = str(accounting_percent(portfolio_variance_pct, 1))
        else:
            portfolio_current = str(accounting_amount(group_data.total, 0))
            portfolio_target = str(accounting_amount(group_data.target_total, 0))
            portfolio_variance = str(
                accounting_amount(group_data.total - group_data.target_total, 0)
            )

        return AllocationTableRow(
            asset_class_id=0,
            asset_class_name=f"{group_label} Total",
            category_code="",
            is_subtotal=False,
            is_group_total=True,
            is_grand_total=False,
            is_cash=False,
            account_type_data=at_columns,
            portfolio_current=portfolio_current,
            portfolio_target=portfolio_target,
            portfolio_variance=portfolio_variance,
        )

    def _build_cash_row(
        self,
        *,
        cash_asset_class_id: int,
        cash_group: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> AllocationTableRow:
        at_columns: list[AccountTypeColumnData] = []

        portfolio_target_total: Decimal = Decimal("0.00")

        for at in account_types:
            at_total_value = getattr(at, "current_total_value", Decimal("0.00"))
            non_cash_target_total = sum(at.target_map.values(), Decimal("0.00"))
            cash_target_pct = Decimal("100.00") - non_cash_target_total
            if cash_target_pct < 0:
                cash_target_pct = Decimal("0.00")

            cash_current_val = cash_group.account_type_totals.get(at.code, Decimal("0.00"))

            if mode == "percent":
                current_pct = (
                    percentage_of(cash_current_val, at_total_value)
                    if at_total_value > 0
                    else Decimal("0.00")
                )
                target_pct = cash_target_pct
                variance_pct = current_pct - target_pct

                portfolio_target_total += at_total_value * (target_pct / Decimal("100.00"))

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_percent(current_pct, 1)),
                        target=str(accounting_percent(target_pct, 1)),
                        variance=str(accounting_percent(variance_pct, 1)),
                        current_raw=current_pct,
                        target_raw=target_pct,
                        variance_raw=variance_pct,
                    )
                )
            else:
                current_val = cash_current_val
                target_val = at_total_value * (cash_target_pct / Decimal("100.00"))
                variance_val = current_val - target_val

                portfolio_target_total += target_val

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_amount(current_val, 0)),
                        target=str(accounting_amount(target_val, 0)),
                        variance=str(accounting_amount(variance_val, 0)),
                        current_raw=current_val,
                        target_raw=target_val,
                        variance_raw=variance_val,
                    )
                )

        if mode == "percent":
            portfolio_current_pct = (
                percentage_of(cash_group.total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_target_pct = (
                percentage_of(portfolio_target_total, portfolio_total_value)
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_variance_pct = portfolio_current_pct - portfolio_target_pct

            portfolio_current = str(accounting_percent(portfolio_current_pct, 1))
            portfolio_target = str(accounting_percent(portfolio_target_pct, 1))
            portfolio_variance = str(accounting_percent(portfolio_variance_pct, 1))
        else:
            portfolio_current = str(accounting_amount(cash_group.total, 0))
            portfolio_target = str(accounting_amount(portfolio_target_total, 0))
            portfolio_variance = str(
                accounting_amount(cash_group.total - portfolio_target_total, 0)
            )

        return AllocationTableRow(
            asset_class_id=cash_asset_class_id,
            asset_class_name="Cash (Calculated)",
            category_code="CASH",
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=False,
            is_cash=True,
            account_type_data=at_columns,
            portfolio_current=portfolio_current,
            portfolio_target=portfolio_target,
            portfolio_variance=portfolio_variance,
        )

    def _build_grand_total_row(
        self,
        *,
        summary: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> AllocationTableRow:
        at_columns: list[AccountTypeColumnData] = []

        for at in account_types:
            current_val = summary.account_type_grand_totals.get(at.code, Decimal("0.00"))

            if mode == "percent":
                current_pct = Decimal("100.00") if at.current_total_value > 0 else Decimal("0.00")
                target_pct = Decimal("100.00") if at.current_total_value > 0 else Decimal("0.00")
                variance_pct = Decimal("0.00")

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_percent(current_pct, 1)),
                        target=str(accounting_percent(target_pct, 1)),
                        variance=str(accounting_percent(variance_pct, 1)),
                        current_raw=current_pct,
                        target_raw=target_pct,
                        variance_raw=variance_pct,
                    )
                )
            else:
                # Total targets should always allocate 100% of an account type's value.
                # If explicit targets are missing/incomplete, treat the remainder as Cash.
                target_val = current_val
                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=str(accounting_amount(current_val, 0)),
                        target=str(accounting_amount(target_val, 0)),
                        variance=str(accounting_amount(Decimal("0.00"), 0)),
                        current_raw=current_val,
                        target_raw=target_val,
                        variance_raw=Decimal("0.00"),
                    )
                )

        if mode == "percent":
            portfolio_current = str(accounting_percent(Decimal("100.00"), 1))
            portfolio_target = str(accounting_percent(Decimal("100.00"), 1))
            portfolio_variance = str(accounting_percent(Decimal("0.00"), 1))
        else:
            portfolio_current = str(accounting_amount(summary.grand_total, 0))
            portfolio_target = str(accounting_amount(summary.grand_total, 0))
            portfolio_variance = str(accounting_amount(Decimal("0.00"), 0))

        return AllocationTableRow(
            asset_class_id=0,
            asset_class_name="Total",
            category_code="",
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=True,
            is_cash=False,
            account_type_data=at_columns,
            portfolio_current=portfolio_current,
            portfolio_target=portfolio_target,
            portfolio_variance=portfolio_variance,
        )

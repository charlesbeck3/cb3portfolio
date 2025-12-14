from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from portfolio.templatetags.portfolio_filters import (
    accounting_amount,
    accounting_percent,
)


@dataclass(frozen=True)
class TargetAccountColumnData:
    account_id: int
    account_name: str
    account_type_id: int
    current: str
    target: str
    vtarget: str
    current_raw: Decimal
    target_raw: Decimal
    vtarget_raw: Decimal
    input_name: str
    input_value: str
    is_input: bool


@dataclass(frozen=True)
class TargetAccountTypeColumnData:
    account_type_id: int
    code: str
    label: str
    current: str
    target_input_name: str
    target_input_value: str
    weighted_target: str
    vtarget: str
    current_raw: Decimal
    target_input_raw: Decimal
    weighted_target_raw: Decimal
    vtarget_raw: Decimal
    is_input: bool


@dataclass(frozen=True)
class TargetAccountTypeGroupData:
    account_type: TargetAccountTypeColumnData
    accounts: list[TargetAccountColumnData]


@dataclass(frozen=True)
class TargetAllocationTableRow:
    asset_class_id: int
    asset_class_name: str
    category_code: str
    is_subtotal: bool
    is_group_total: bool
    is_grand_total: bool
    is_cash: bool
    groups: list[TargetAccountTypeGroupData]
    portfolio_current: str
    portfolio_target: str
    portfolio_vtarget: str
    row_css_class: str


class TargetAllocationTableBuilder:
    def build_rows(
        self,
        *,
        summary: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        cash_asset_class_id: int | None,
    ) -> list[TargetAllocationTableRow]:
        rows: list[TargetAllocationTableRow] = []

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
                            summary=summary,
                        )
                    )

                if len(cat_data.asset_classes) > 1:
                    category_label = category_labels.get(category_code, category_code)
                    rows.append(
                        self._build_category_row(
                            label=f"{category_label} Total",
                            category_code=category_code,
                            current_by_at=cat_data.account_type_totals,
                            target_by_at=cat_data.account_type_target_totals,
                            variance_pct_by_at=cat_data.account_type_variance_pct,
                            current_by_account=cat_data.account_totals,
                            target_by_account=cat_data.account_target_totals,
                            portfolio_current=cat_data.total,
                            portfolio_target=cat_data.target_total,
                            portfolio_variance=cat_data.variance_total,
                            account_types=account_types,
                            portfolio_total_value=portfolio_total_value,
                            mode=effective_mode,
                            is_subtotal=True,
                            is_group_total=False,
                            is_grand_total=False,
                            is_cash=False,
                            summary=summary,
                        )
                    )

            if group_data.asset_class_count > 1 and len(group_data.categories) > 1:
                group_label = group_data.label or group_labels.get(group_code, group_code)
                rows.append(
                    self._build_category_row(
                        label=f"{group_label} Total",
                        category_code="",
                        current_by_at=group_data.account_type_totals,
                        target_by_at=group_data.account_type_target_totals,
                        variance_pct_by_at=group_data.account_type_variance_pct,
                        current_by_account=group_data.account_totals,
                        target_by_account=group_data.account_target_totals,
                        portfolio_current=group_data.total,
                        portfolio_target=group_data.target_total,
                        portfolio_variance=group_data.variance_total,
                        account_types=account_types,
                        portfolio_total_value=portfolio_total_value,
                        mode=effective_mode,
                        is_subtotal=False,
                        is_group_total=True,
                        is_grand_total=False,
                        is_cash=False,
                        summary=summary,
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
                        summary=summary,
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
        summary: Any,
    ) -> TargetAllocationTableRow:
        return self._build_category_row(
            label=ac_name,
            summary=summary,
            category_code=category_code,
            current_by_at={
                at.code: getattr(ac_data.account_types.get(at.code), "current", Decimal("0.00"))
                for at in account_types
            },
            target_by_at={
                at.code: getattr(ac_data.account_types.get(at.code), "target", Decimal("0.00"))
                for at in account_types
            },
            variance_pct_by_at={
                at.code: getattr(
                    ac_data.account_types.get(at.code), "variance_pct", Decimal("0.00")
                )
                for at in account_types
            },
            current_by_account={},
            target_by_account={},
            portfolio_current=ac_data.total,
            portfolio_target=ac_data.target_total,
            portfolio_variance=ac_data.variance_total,
            account_types=account_types,
            portfolio_total_value=portfolio_total_value,
            mode=mode,
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=False,
            is_cash=False,
            asset_class_id=ac_data.id or 0,


        )

    def _build_cash_row(
        self,
        *,
        cash_asset_class_id: int,
        cash_group: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        summary: Any,
    ) -> TargetAllocationTableRow:
        current_by_at = {}
        target_by_at = {}
        variance_pct_by_at = {}

        portfolio_target_total = Decimal("0.00")

        for at in account_types:
            at_total_value = getattr(at, "current_total_value", Decimal("0.00"))
            non_cash_target_total = sum(at.target_map.values(), Decimal("0.00"))
            cash_target_pct = Decimal("100.00") - non_cash_target_total
            if cash_target_pct < 0:
                cash_target_pct = Decimal("0.00")

            cash_current_val = cash_group.account_type_totals.get(at.code, Decimal("0.00"))
            current_by_at[at.code] = cash_current_val

            if mode == "percent":
                target_by_at[at.code] = Decimal("0.00")  # Not used for display in PCT mode
                current_pct = (
                    (cash_current_val / at_total_value) * 100
                    if at_total_value > 0
                    else Decimal("0.00")
                )
                variance_pct_by_at[at.code] = current_pct - cash_target_pct
                portfolio_target_total += at_total_value * (cash_target_pct / Decimal("100.00"))
            else:
                target_val = at_total_value * (cash_target_pct / Decimal("100.00"))
                target_by_at[at.code] = target_val
                variance_pct_by_at[at.code] = Decimal("0.00")  # Not used in dollar mode
                portfolio_target_total += target_val

        return self._build_category_row(
            label="Cash",
            category_code="CASH",
            current_by_at=current_by_at,
            target_by_at=target_by_at,
            variance_pct_by_at=variance_pct_by_at,
            current_by_account={},
            target_by_account={},
            portfolio_current=cash_group.total,
            portfolio_target=portfolio_target_total,
            portfolio_variance=cash_group.total - portfolio_target_total,
            account_types=account_types,
            portfolio_total_value=portfolio_total_value,
            mode=mode,
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=False,
            is_cash=True,
            asset_class_id=cash_asset_class_id,

            summary=summary,
        )

    def _build_grand_total_row(
        self,
        *,
        summary: Any,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> TargetAllocationTableRow:
        current_by_at = {}
        target_by_at = {}
        variance_pct_by_at = {}

        for at in account_types:
            current_val = summary.account_type_grand_totals.get(at.code, Decimal("0.00"))
            current_by_at[at.code] = current_val
            target_by_at[at.code] = current_val  # Target = Current for Grand Total
            variance_pct_by_at[at.code] = Decimal("0.00")

        return self._build_category_row(
            label="Total",
            category_code="",
            current_by_at=current_by_at,
            target_by_at=target_by_at,
            variance_pct_by_at=variance_pct_by_at,
            current_by_account={},
            target_by_account={},
            portfolio_current=summary.grand_total,
            portfolio_target=summary.grand_total,
            portfolio_variance=Decimal("0.00"),
            account_types=account_types,
            portfolio_total_value=portfolio_total_value,
            mode=mode,
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=True,
            is_cash=False,
            summary=summary,
        )

    def _build_category_row(
        self,
        *,
        label: str,
        category_code: str,
        current_by_at: dict[str, Decimal],
        target_by_at: dict[str, Decimal],
        variance_pct_by_at: dict[str, Decimal],
        current_by_account: dict[int, Decimal],
        target_by_account: dict[int, Decimal],
        portfolio_current: Decimal,
        portfolio_target: Decimal,
        portfolio_variance: Decimal,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        is_subtotal: bool,
        is_group_total: bool,
        is_grand_total: bool,
        is_cash: bool,
        summary: Any,
        asset_class_id: int = 0,
    ) -> TargetAllocationTableRow:
        groups = []

        # Create CSS class for row highlighting/styling
        row_css_class = ""
        if is_subtotal:
            row_css_class = "table-secondary fw-bold"
        elif is_group_total:
            row_css_class = "table-primary fw-bold"
        elif is_grand_total:
            row_css_class = "table-dark fw-bold"

        if is_cash:
            row_css_class += " table-info"

        # Calculate Portfolio Variance
        if mode == "percent":
            portfolio_current_fmt = str(
                accounting_percent(
                    (portfolio_current / portfolio_total_value) * 100
                    if portfolio_total_value
                    else 0,
                    1,
                )
            )
            portfolio_target_fmt = str(
                accounting_percent(
                    (portfolio_target / portfolio_total_value) * 100
                    if portfolio_total_value
                    else 0,
                    1,
                )
            )
            # Variance for portfolio total in percent mode
            # For asset rows: calculated by SummaryService?
            # For calculated rows above: passed in.
            # But wait, `portfolio_variance` passed in is DOLLAR variance for some calls?
            # Recheck `_build_cash_row`: passes `cash_group.total - portfolio_target_total`. That's dollars.
            # So we need to convert to percent if mode is percent.
            # SummaryService calculates `ac_data.variance_total` as dollars.
            p_var_pct = (
                (portfolio_variance / portfolio_total_value) * 100
                if portfolio_total_value > 0
                else Decimal("0.00")
            )
            portfolio_vtarget_fmt = str(accounting_percent(p_var_pct, 1))

        else:
            portfolio_current_fmt = str(accounting_amount(portfolio_current, 0))
            portfolio_target_fmt = str(accounting_amount(portfolio_target, 0))
            portfolio_vtarget_fmt = str(accounting_amount(portfolio_variance, 0))

        for at in account_types:
            accounts = []
            # Iterate accounts within type
            for account in getattr(at, "active_accounts", []):
                # Get current value for account
                acc_current = current_by_account.get(account.id, Decimal("0.00"))
                # Get target (only if not grand total/calculated?)
                acc_target = target_by_account.get(account.id, Decimal("0.00"))

                # Determine raw values
                # For input fields (Asset Rows), we need to check if there is an input value.
                # But inputs are only for Asset Rows?
                # Yes, `is_subtotal` etc are False.

                is_input = not (is_subtotal or is_group_total or is_grand_total or is_cash)
                input_name = f"target_account_{account.id}_{asset_class_id}"
                input_val = ""

                if is_input:
                    # Check for override first
                    configured_pct = account.target_map.get(asset_class_id)
                    if configured_pct is None:
                        # Fallback to account type default
                        configured_pct = at.target_map.get(asset_class_id, Decimal("0.00"))

                    input_val = str(configured_pct)

                # Variance
                # If row is asset, variance is per account?
                # SummaryService calculates variance per account-type, but maybe not per account-asset-class?
                # `cat_data.account_variance_totals` exists.
                # But `ac_data` doesn't seem to have per-account variance in `SummaryService`.
                # Wait, step 19 doesn't show per-account variance on AssetClassEntry.
                # It shows `account_asset_targets` on summary.
                # So we can calculate it: Current - TargetDollars.
                # TargetDollars = AccountTotal * (ConfiguredPct / 100).

                acc_total_val = getattr(account, "current_total_value", Decimal("0.00"))
                acc_current_pct = (acc_current / acc_total_val * 100) if acc_total_val > 0 else Decimal("0.00")

                acc_target_dollars = Decimal("0.00")
                if is_input:
                    acc_target_dollars = summary.account_asset_targets[account.id].get(
                        asset_class_id, Decimal("0.00")
                    )
                else:
                    acc_target_dollars = acc_target

                acc_target_pct = (acc_target_dollars / acc_total_val * 100) if acc_total_val > 0 else Decimal("0.00")
                acc_variance = acc_current - acc_target_dollars
                acc_variance_pct = acc_current_pct - acc_target_pct

                if mode == "percent":
                    current_disp = str(accounting_percent(acc_current_pct, 1))
                    if is_input:
                        # Input fields handle their own display value (input_val)
                        target_disp = str(accounting_amount(acc_target_dollars, 0)) # Not used?
                    else:
                        target_disp = str(accounting_percent(acc_target_pct, 1))
                    vtarget_disp = str(accounting_percent(acc_variance_pct, 1))
                else:
                    current_disp = str(accounting_amount(acc_current, 0))
                    target_disp = str(accounting_amount(acc_target_dollars, 0))
                    vtarget_disp = str(accounting_amount(acc_variance, 0))

                accounts.append(
                    TargetAccountColumnData(
                        account_id=account.id,
                        account_name=account.name,
                        account_type_id=at.id,
                        current=current_disp,
                        target=target_disp,
                        vtarget=vtarget_disp,
                        current_raw=acc_current,
                        target_raw=acc_target_dollars,
                        vtarget_raw=acc_variance,
                        input_name=input_name,
                        input_value=input_val,
                        is_input=is_input,
                    )
                )

            # Account Type Group Columns
            at_code = at.code
            at_current = current_by_at.get(at_code, Decimal("0.00"))
            at_target = target_by_at.get(at_code, Decimal("0.00"))  # Dollars

            at_variance_pct = variance_pct_by_at.get(at_code, Decimal("0.00"))

            # Weighted Target (Asset Class Only)
            # If subtotal, we sum?
            # If asset class, it's the "Average" target?
            # Or just "Target %"?
            # Existing template logic: `{{ at_data.target_pct }}`.
            # In `AllocationTableBuilder`: we calculated `target_pct`.
            # Here: `at_target` is dollars (from summary).
            # Convert to % of AccountType Total.
            at_total_val = getattr(at, "current_total_value", Decimal("0.00"))

            if at_total_val > 0:
                at_weighted_target_pct = (at_target / at_total_val) * 100
                at_current_pct = (at_current / at_total_val) * 100
            else:
                at_weighted_target_pct = Decimal("0.00")
                at_current_pct = Decimal("0.00")

            # Input for Account Type (Apply to All - Default Target)
            at_input_name = f"target_{at.id}_{asset_class_id}"
            at_configured_pct = at.target_map.get(asset_class_id, Decimal("0.00"))
            at_input_val = str(at_configured_pct)

            if mode == "percent":
                # Display Percentages
                current_disp = str(accounting_percent(at_current_pct, 1))
                # Weighted Target is the target %
                weighted_disp = str(accounting_percent(at_weighted_target_pct, 1))
                vtarget_disp = str(accounting_percent(at_current_pct - at_weighted_target_pct, 1))
            else:
                # Display Dollars
                current_disp = str(accounting_amount(at_current, 0))
                weighted_disp = str(accounting_amount(at_target, 0))
                vtarget_disp = str(accounting_amount(at_current - at_target, 0))

            groups.append(
                TargetAccountTypeGroupData(
                    account_type=TargetAccountTypeColumnData(
                        account_type_id=at.id,
                        code=at.code,
                        label=at.label,
                        current=current_disp,
                        target_input_name=at_input_name,
                        target_input_value=at_input_val,
                        weighted_target=weighted_disp,
                        vtarget=vtarget_disp,
                        current_raw=at_current,
                        target_input_raw=Decimal("0.00"),  # placeholder
                        weighted_target_raw=at_weighted_target_pct
                        if mode == "percent"
                        else at_target,
                        vtarget_raw=at_variance_pct if mode == "percent" else (at_current - at_target),
                        is_input=is_input,
                    ),
                    accounts=accounts,
                )
            )

        return TargetAllocationTableRow(
            asset_class_id=asset_class_id,
            asset_class_name=label,
            category_code=category_code,
            is_subtotal=is_subtotal,
            is_group_total=is_group_total,
            is_grand_total=is_grand_total,
            is_cash=is_cash,
            groups=groups,
            portfolio_current=portfolio_current_fmt,
            portfolio_target=portfolio_target_fmt,
            portfolio_vtarget=portfolio_vtarget_fmt,
            row_css_class=row_css_class,
        )

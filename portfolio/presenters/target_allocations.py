from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import pandas as pd

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
        allocations: dict[str, Any],  # expected to be dict of DataFrames from engine
        ac_meta: dict[str, Any],  # Name -> {id, group_code, group_label, category_code, category_label}
        hierarchy: dict[str, dict[str, list[str]]], # GroupCode -> CatCode -> [AC Names]
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        cash_asset_class_id: int | None,
        account_targets: dict[int, dict[int, Decimal]], # Account ID -> AC ID -> Target Dollars (for variance)
    ) -> list[TargetAllocationTableRow]:
        rows: list[TargetAllocationTableRow] = []
        effective_mode = "money" if mode == "dollar" else mode

        # DataFrames
        df_asset_class = allocations.get("by_asset_class") # Index: Asset_Class
        df_account_type = allocations.get("by_account_type") # Index: Account_Type, Cols: AC_dollars...
        df_account = allocations.get("by_account") # Index: Account_Name (Careful map via ID/Name)

        # We need to map Account ID -> DataFrame Column/Index?
        # df_account index is "Account_Name". We have Account objects in `account_types`.
        # Account objects have `.name`.

        # Iterate Hierarchy
        # Hierarchy: Group -> Category -> AssetClasses

        # We need a defined sort order for Groups?
        # Typically passed in hierarchy should be sorted, or we sort by keys/metadata.
        # Assuming hierarchy keys are sorted or we rely on insertion order if py3.7+ (valid).

        # To match previous behavior (sort by total value?), we might need to sort 'hierarchy' keys based on df totals.
        # Let's assume hierarchy passed in is already sorted or we iterate simply.
        # Previous service sorted by value.

        # Let's iterate what we were given.

        for group_code, categories in hierarchy.items():
            # Calculate Group Subtotal Data
            # We need to sum up all ACs in this group from the DataFrames
            group_acs = [ac for cats in categories.values() for ac in cats]
            self._sum_asset_classes(df_asset_class, df_account_type, df_account, group_acs, account_types)

            # Check if we need a Group Total row (at the end usually, but we need data for it)
            # The loop structure in previous was: Categories -> ACs -> CategoryTotal -> (GroupTotal)

            sum(len(acs) for acs in categories.values())

            for category_code, ac_names in categories.items():
                # Filter out Cash if needed
                ac_names_filtered = [
                    ac for ac in ac_names
                    if not (cash_asset_class_id is not None and ac_meta.get(ac, {}).get('id') == cash_asset_class_id)
                ]

                if not ac_names_filtered:
                    continue

                for ac_name in ac_names_filtered:
                     meta = ac_meta.get(ac_name, {})
                     # Get Current Values from DataFrames
                     # Portfolio Level
                     # Lookup df_asset_class.loc[ac_name]
                     portfolio_current = Decimal("0.00")
                     if df_asset_class is not None and ac_name in df_asset_class.index:
                         portfolio_current = Decimal(float(df_asset_class.loc[ac_name, "Dollar_Amount"]))

                     # Account Type Level
                     # df_account_type columns are "Asset_Class_dollars" ... no wait.
                     # index is AccountType Label. Columns are AC names?
                     # Let's re-verify `_calculate_by_account_type`.
                     # Result: Index=Account_Type, Cols="AC_Name_dollars", "AC_Name_pct"

                     at_currents = {}
                     for at in account_types:
                         col_name = f"{ac_name}_dollars"
                         val = Decimal("0.00")
                         if df_account_type is not None and at.label in df_account_type.index:
                              if col_name in df_account_type.columns:
                                   val = Decimal(float(df_account_type.loc[at.label, col_name]))
                         at_currents[at.id] = val

                     # Account Level
                     # df_account: Index=Account_Name, Cols="AC_Name_dollars"
                     acc_currents = {}
                     for at in account_types:
                         for acc in getattr(at, "active_accounts", []):
                             col_name = f"{ac_name}_dollars"
                             val = Decimal("0.00")
                             if df_account is not None and acc.name in df_account.index:
                                 if col_name in df_account.columns:
                                     val = Decimal(float(df_account.loc[acc.name, col_name]))
                             acc_currents[acc.id] = val

                     rows.append(self._build_asset_row(
                         ac_name=ac_name,
                         ac_id=meta.get('id', 0),
                         category_code=category_code,
                         portfolio_current=portfolio_current,
                         at_currents=at_currents,
                         acc_currents=acc_currents,
                         account_types=account_types,
                         portfolio_total_value=portfolio_total_value,
                         mode=effective_mode,
                         account_targets=account_targets
                     ))

                # Category Subtotal
                if len(ac_names_filtered) > 1:
                    cat_label = ac_meta.get(ac_names_filtered[0], {}).get('category_label', category_code)

                    # Sum for category
                    cat_total_row = self._sum_asset_classes(df_asset_class, df_account_type, df_account, ac_names_filtered, account_types)

                    rows.append(self._build_calculated_row(
                        label=f"{cat_label} Total",
                        category_code=category_code,
                        data=cat_total_row,
                        account_types=account_types,
                        portfolio_total_value=portfolio_total_value,
                        mode=effective_mode,
                        is_subtotal=True,
                        account_targets=account_targets,
                        ac_names=ac_names_filtered,
                        ac_meta=ac_meta,  # ADDED
                    ))

            # Group Total
            # Condition: >1 asset class total in group AND >1 category (implied by previous logic, roughly)
            # Logic from old builder: if group_data.asset_class_count > 1 and len(group_data.categories) > 1
            filtered_cats = [c for c, acs in categories.items() if any(
                not (cash_asset_class_id is not None and ac_meta.get(ac, {}).get('id') == cash_asset_class_id)
                for ac in acs
            )]

            total_filtered_acs = 0
            for cats in categories.values():
                 total_filtered_acs += len([
                    ac for ac in cats
                    if not (cash_asset_class_id is not None and ac_meta.get(ac, {}).get('id') == cash_asset_class_id)
                ])

            if total_filtered_acs > 1 and len(filtered_cats) > 1:
                group_label = ac_meta.get(group_acs[0], {}).get('group_label', group_code)
                # Re-calculate filtered group total data (exclude cash)
                filtered_group_acs = [
                    ac for ac in group_acs
                    if not (cash_asset_class_id is not None and ac_meta.get(ac, {}).get('id') == cash_asset_class_id)
                ]
                group_data_sum = self._sum_asset_classes(df_asset_class, df_account_type, df_account, filtered_group_acs, account_types)

                rows.append(self._build_calculated_row(
                    label=f"{group_label} Total",
                    category_code="",
                    data=group_data_sum,
                    account_types=account_types,
                    portfolio_total_value=portfolio_total_value,
                    mode=effective_mode,
                    is_group_total=True,
                    account_targets=account_targets,
                    ac_names=filtered_group_acs,
                    ac_meta=ac_meta,  # ADDED
                ))

        # Cash Row
        if cash_asset_class_id is not None:
             # Find cash AC name
             cash_ac_name = next((name for name, m in ac_meta.items() if m.get('id') == cash_asset_class_id), None)
             if cash_ac_name:
                 # Get Cash Data
                 portfolio_current = Decimal("0.00")
                 if df_asset_class is not None and cash_ac_name in df_asset_class.index:
                     portfolio_current = Decimal(float(df_asset_class.loc[cash_ac_name, "Dollar_Amount"]))

                 at_currents = {}
                 for at in account_types:
                     col_name = f"{cash_ac_name}_dollars"
                     val = Decimal("0.00")
                     if df_account_type is not None and at.label in df_account_type.index and col_name in df_account_type.columns:
                         val = Decimal(float(df_account_type.loc[at.label, col_name]))
                     at_currents[at.id] = val

                 acc_currents = {}
                 for at in account_types:
                     for acc in getattr(at, "active_accounts", []):
                         col_name = f"{cash_ac_name}_dollars"
                         val = Decimal("0.00")
                         if df_account is not None and acc.name in df_account.index and col_name in df_account.columns:
                             val = Decimal(float(df_account.loc[acc.name, col_name]))
                         acc_currents[acc.id] = val

                 rows.append(self._build_cash_row(
                     cash_asset_class_id=cash_asset_class_id,
                     current_data={'portfolio': portfolio_current, 'at': at_currents, 'acc': acc_currents},
                     account_types=account_types,
                     portfolio_total_value=portfolio_total_value,
                     mode=effective_mode
                 ))

        # Grand Total
        # Sum of everything in df_asset_class 'Dollar_Amount'
        grand_total = Decimal("0.00")
        if df_asset_class is not None and not df_asset_class.empty:
            grand_total = Decimal(float(df_asset_class["Dollar_Amount"].sum()))

        # AT Grand Totals
        at_grand_totals = {}
        for at in account_types:
            at_grand_totals[at.id] = getattr(at, "current_total_value", Decimal("0.00"))

        # Account Grand Totals (implied from at.active_accounts)

        rows.append(self._build_grand_total_row(
            grand_total=grand_total,
            at_grand_totals=at_grand_totals,
            account_types=account_types,
            portfolio_total_value=portfolio_total_value,
            mode=effective_mode
        ))

        return rows

    def _sum_asset_classes(
        self,
        df_ac: Optional[pd.DataFrame],
        df_at: Optional[pd.DataFrame],
        df_acc: Optional[pd.DataFrame],
        ac_names: list[str],
        account_types: list[Any],
    ) -> dict[str, Any]:
        """Helper to sum values for a list of asset classes."""
        res: dict[str, Any] = {
            "portfolio": Decimal("0.00"),
            "at": defaultdict(Decimal),
            "acc": defaultdict(Decimal),
        }

        for ac in ac_names:
            # Portfolio
            if df_ac is not None and ac in df_ac.index:
                res["portfolio"] += Decimal(float(df_ac.loc[ac, "Dollar_Amount"]))

            col_name = f"{ac}_dollars"

            # AT
            if df_at is not None and col_name in df_at.columns:
                for at in account_types:
                    if at.label in df_at.index:
                        res["at"][at.id] += Decimal(float(df_at.loc[at.label, col_name]))

            # Acc
            if df_acc is not None and col_name in df_acc.columns:
                for at in account_types:
                    for acc in getattr(at, "active_accounts", []):
                        if acc.name in df_acc.index:
                            res["acc"][acc.id] += Decimal(float(df_acc.loc[acc.name, col_name]))

        return res

    def _build_asset_row(
        self,
        *,
        ac_name: str,
        ac_id: int,
        category_code: str,
        portfolio_current: Decimal,
        at_currents: dict[int, Decimal],
        acc_currents: dict[int, Decimal],
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        account_targets: dict[int, dict[int, Decimal]],
    ) -> TargetAllocationTableRow:

        # Calculate Targets & Variances "on the fly" since they depend on configuration (Target Map)
        # AC Data
        portfolio_target = Decimal("0.00")

        # Build Groups (AT Columns)
        groups = []

        for at in account_types:
            at_current = at_currents.get(at.id, Decimal("0.00"))

            # AT Target Logic
            # Asset Row: we don't display a single "AT Target" for the asset?
            # Actually we do: Weighted Target column in "Account Type" section.
            # But the logic for that in `_build_category_row` was:
            # `at_target` (sum of defaults?)
            # Wait, `TargetAllocationTableBuilder` logic for "Weighted Target":
            # "Weighted Target is the target %"
            # It uses `at.target_map.get(ac_id)`.

            at_configured_pct = at.target_map.get(ac_id, Decimal("0.00"))
            at_total_val = getattr(at, "current_total_value", Decimal("0.00"))

            # Calculate what the target *value* would be based on default
            at_total_val * (at_configured_pct / Decimal("100.00"))

            # Wait, the "Weighted Target" displayed should be the sum of ACTUAL targets of the accounts?
            # Or the Default Target?
            # In the previous code `_build_row`:
            # `tgt_pct = ac_targets.get(at.code)` -> Sum of target % map.
            # It seems it was calculating based on the *assignments*.

            # Let's match the visual expectation.
            # If I override an account, does the AT column update?
            # Yes, usually.
            # But here `at_configured_pct` is the DEFAULT.
            # The "Weighted Target" column usually shows the *aggregate* target of all accounts?
            # Or just the setting?
            # In `_build_asset_row` (old): `target_by_at` came from `ac_data.account_types[code].target`.
            # `ac_data` came from SummaryService which aggregated Account targets.

            # So, we must aggregate Account Targets to get AT Target.
            at_target_val = Decimal("0.00")

            accounts_data = []
            for acc in getattr(at, "active_accounts", []):
                acc_current = acc_currents.get(acc.id, Decimal("0.00"))
                acc_total_val = getattr(acc, "current_total_value", Decimal("0.00"))

                # Acc Target
                # Check override
                if acc.target_map and ac_id in acc.target_map:
                    pct = acc.target_map[ac_id]
                else:
                    # Check acc specific override map (if strategy applied) logic is handled by ViewService populating target_map
                    # ViewService populates `acc.target_map` with the effective strategy targets.
                    # If empty, it means use AT defaults?
                    # `TargetAllocationViewService` line 96: `acc.target_map = overrides_map.get(acc.id, {})`.
                    # If acc has strategy -> overrides_map has it.
                    # If acc has NO strategy -> overrides_map is empty.
                    # Logic in old builder line 444: `configured_pct = account.target_map.get(...)`.
                    # `if configured_pct is None: fallback to at.target_map`.

                    pct = acc.target_map.get(ac_id)
                    if pct is None:
                        pct = at.target_map.get(ac_id, Decimal("0.00"))

                acc_target_val = acc_total_val * (pct / Decimal("100.00"))

                # Check for explicit input via `account_targets` (passed from View/Calc?)
                # Actually, `account_targets` arg is mostly for Variance calc if we wanted to use pre-calc.
                # But here we are calculating strictly from `pct`.
                # Why did I add `account_targets` arg? To replace `summary.account_asset_targets`.
                # Let's use `acc_target_val` calculated here.

                at_target_val += acc_target_val

                # Acc Variance
                acc_variance = acc_current - acc_target_val

                input_name = f"target_account_{acc.id}_{ac_id}"
                input_val = str(pct)

                # Formatting
                if mode == "percent":
                   c_disp = str(accounting_percent((acc_current/acc_total_val*100) if acc_total_val else 0, 1))
                   t_disp = str(accounting_percent((acc_target_val/acc_total_val*100) if acc_total_val else 0, 1))
                   v_disp = str(accounting_percent(((acc_current/acc_total_val*100) - (acc_target_val/acc_total_val*100)) if acc_total_val else 0, 1))
                else:
                   c_disp = str(accounting_amount(acc_current, 0))
                   t_disp = str(accounting_amount(acc_target_val, 0))
                   v_disp = str(accounting_amount(acc_variance, 0))

                accounts_data.append(TargetAccountColumnData(
                    account_id=acc.id,
                    account_name=acc.name,
                    account_type_id=at.id,
                    current=c_disp,
                    target=t_disp,
                    vtarget=v_disp,
                    current_raw=acc_current,
                    target_raw=acc_target_val,
                    vtarget_raw=acc_variance,
                    input_name=input_name,
                    input_value=input_val,
                    is_input=True
                ))

            # AT Level Display
            at_variance = at_current - at_target_val
            portfolio_target += at_target_val

            at_input_name = f"target_{at.id}_{ac_id}"
            at_input_val = str(at_configured_pct)

            if mode == "percent":
                at_current_pct = (at_current / at_total_val * 100) if at_total_val else Decimal("0.00")
                at_target_pct = (at_target_val / at_total_val * 100) if at_total_val else Decimal("0.00")

                c_disp = str(accounting_percent(at_current_pct, 1))
                w_disp = str(accounting_percent(at_target_pct, 1)) # Weighted Target
                v_disp = str(accounting_percent(at_current_pct - at_target_pct, 1))
            else:
                c_disp = str(accounting_amount(at_current, 0))
                w_disp = str(accounting_amount(at_target_val, 0))
                v_disp = str(accounting_amount(at_variance, 0))

            groups.append(TargetAccountTypeGroupData(
                account_type=TargetAccountTypeColumnData(
                    account_type_id=at.id,
                    code=at.code,
                    label=at.label,
                    current=c_disp,
                    target_input_name=at_input_name,
                    target_input_value=at_input_val,
                    weighted_target=w_disp,
                    vtarget=v_disp,
                    current_raw=at_current,
                    target_input_raw=at_configured_pct,
                    weighted_target_raw=at_target_val, # Pct or Money depending on mode? Struct says raw...
                    vtarget_raw=at_variance,
                    is_input=True
                ),
                accounts=accounts_data
            ))

        # Portfolio Variance
        portfolio_variance = portfolio_current - portfolio_target

        if mode == "percent":
             p_current_pct = (portfolio_current / portfolio_total_value * 100) if portfolio_total_value else Decimal(0)
             p_target_pct = (portfolio_target / portfolio_total_value * 100) if portfolio_total_value else Decimal(0)

             p_c_disp = str(accounting_percent(p_current_pct, 1))
             p_t_disp = str(accounting_percent(p_target_pct, 1))
             p_v_disp = str(accounting_percent(p_current_pct - p_target_pct, 1))
        else:
             p_c_disp = str(accounting_amount(portfolio_current, 0))
             p_t_disp = str(accounting_amount(portfolio_target, 0))
             p_v_disp = str(accounting_amount(portfolio_variance, 0))

        return TargetAllocationTableRow(
            asset_class_id=ac_id,
            asset_class_name=ac_name,
            category_code=category_code,
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=False,
            is_cash=False,
            groups=groups,
            portfolio_current=p_c_disp,
            portfolio_target=p_t_disp,
            portfolio_vtarget=p_v_disp,
            row_css_class=""
        )

    def _build_calculated_row(
        self,
        label: str,
        category_code: str,
        data: dict[str, Any],
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        ac_names: list[str],
        ac_meta: dict[str, Any],  # ADDED
        is_subtotal: bool = False,
        is_group_total: bool = False,
        account_targets: Optional[dict[int, dict[int, Decimal]]] = None,
    ) -> TargetAllocationTableRow:
        # data: {'portfolio': val, 'at': {id: val}, 'acc': {id: val}} (Current Values only)

        portfolio_current = data['portfolio']
        portfolio_target = Decimal("0.00")

        groups = []

        for at in account_types:
            at_current = data['at'].get(at.id, Decimal("0.00"))

            at_target_val = Decimal("0.00")

            at_total_val = getattr(at, "current_total_value", Decimal("0.00"))

            accounts_data = []

            for acc in getattr(at, "active_accounts", []):
                acc_current = data['acc'].get(acc.id, Decimal("0.00"))
                acc_total_val = getattr(acc, "current_total_value", Decimal("0.00"))

                # Calculate Acc Target
                acc_target_val = Decimal("0.00")

                for ac_name in ac_names:
                    # Look up AC ID
                    meta = ac_meta.get(ac_name)
                    if meta:
                        ac_id = meta.get('id')
                        if ac_id:
                            # Use acc.target_map
                            pct = Decimal("0.00")
                            if acc.target_map and ac_id in acc.target_map:
                                pct = acc.target_map[ac_id]
                            else:
                                pct = acc.target_map.get(ac_id, Decimal("0.00"))

                            acc_target_val += acc_total_val * (pct / Decimal("100.00"))

                at_target_val += acc_target_val

                acc_variance = acc_current - acc_target_val

                # Formatting
                if mode == "percent":
                   c_disp = str(accounting_percent((acc_current/acc_total_val*100) if acc_total_val else 0, 1))
                   t_disp = str(accounting_percent((acc_target_val/acc_total_val*100) if acc_total_val else 0, 1))
                   v_disp = str(accounting_percent(((acc_current/acc_total_val*100) - (acc_target_val/acc_total_val*100)) if acc_total_val else 0, 1))
                else:
                   c_disp = str(accounting_amount(acc_current, 0))
                   t_disp = str(accounting_amount(acc_target_val, 0))
                   v_disp = str(accounting_amount(acc_variance, 0))

                accounts_data.append(TargetAccountColumnData(
                    account_id=acc.id,
                    account_name=acc.name,
                    account_type_id=at.id,
                    current=c_disp,
                    target=t_disp,
                    vtarget=v_disp,
                    current_raw=acc_current,
                    target_raw=acc_target_val,
                    vtarget_raw=acc_variance,
                    input_name="",
                    input_value="",
                    is_input=False
                ))

            portfolio_target += at_target_val
            at_variance = at_current - at_target_val

            # Formatting AT
            weighted_target_raw_val = at_target_val

            if mode == "percent":
                at_current_pct = (at_current / at_total_val * 100) if at_total_val else Decimal("0.00")
                at_target_pct = (at_target_val / at_total_val * 100) if at_total_val else Decimal("0.00")

                c_disp = str(accounting_percent(at_current_pct, 1))
                w_disp = str(accounting_percent(at_target_pct, 1))
                v_disp = str(accounting_percent(at_current_pct - at_target_pct, 1))

                weighted_target_raw_val = at_target_pct
            else:
                c_disp = str(accounting_amount(at_current, 0))
                w_disp = str(accounting_amount(at_target_val, 0))
                v_disp = str(accounting_amount(at_variance, 0))

            groups.append(TargetAccountTypeGroupData(
                account_type=TargetAccountTypeColumnData(
                    account_type_id=at.id,
                    code=at.code,
                    label=at.label,
                    current=c_disp,
                    target_input_name="",
                    target_input_value="",
                    weighted_target=w_disp,
                    vtarget=v_disp,
                    current_raw=at_current,
                    target_input_raw=Decimal(0),
                    weighted_target_raw=weighted_target_raw_val,
                    vtarget_raw=at_variance,
                    is_input=False
                ),
                accounts=accounts_data
            ))

        # Portfolio Formatting
        portfolio_variance = portfolio_current - portfolio_target
        if mode == "percent":
             p_current_pct = (portfolio_current / portfolio_total_value * 100) if portfolio_total_value else Decimal(0)
             p_target_pct = (portfolio_target / portfolio_total_value * 100) if portfolio_total_value else Decimal(0)

             p_c_disp = str(accounting_percent(p_current_pct, 1))
             p_t_disp = str(accounting_percent(p_target_pct, 1))
             p_v_disp = str(accounting_percent(p_current_pct - p_target_pct, 1))
        else:
             p_c_disp = str(accounting_amount(portfolio_current, 0))
             p_t_disp = str(accounting_amount(portfolio_target, 0))
             p_v_disp = str(accounting_amount(portfolio_variance, 0))

        return TargetAllocationTableRow(
             asset_class_id=0,
             asset_class_name=label,
             category_code=category_code,
             is_subtotal=is_subtotal,
             is_group_total=is_group_total,
             is_grand_total=False,
             is_cash=False,
             groups=groups,
             portfolio_current=p_c_disp,
             portfolio_target=p_t_disp,
             portfolio_vtarget=p_v_disp,
             row_css_class="table-secondary fw-bold" if is_subtotal else "table-primary fw-bold"
        )

    def _build_cash_row(
        self,
        *,
        cash_asset_class_id: int,
        current_data: dict, # {portfolio, at, acc}
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> TargetAllocationTableRow:
        # Cash Row Logic
        portfolio_current = current_data['portfolio']
        portfolio_target = Decimal("0.00")

        groups = []

        for at in account_types:
            at_current = current_data['at'].get(at.id, Decimal("0.00"))
            at_total_val = getattr(at, "current_total_value", Decimal("0.00"))

            # Calculate AT Target (Cash remainder)
            # Sum non-cash targets
            non_cash_target_total = Decimal("0.00")
            for ac_id, val in at.target_map.items():
                if ac_id != cash_asset_class_id:
                    non_cash_target_total += val

            cash_target_pct = Decimal("100.00") - non_cash_target_total
            if cash_target_pct < 0: cash_target_pct = Decimal("0.00")

            # AT Target Value
            at_target_val = at_total_val * (cash_target_pct / Decimal("100.00"))
            portfolio_target += at_target_val

            # Accounts
            accounts_data = []
            at_agg_target_val = Decimal("0.00")

            for acc in getattr(at, "active_accounts", []):
                acc_current = current_data['acc'].get(acc.id, Decimal("0.00"))
                acc_total_val = getattr(acc, "current_total_value", Decimal("0.00"))

                # Acc Target
                if acc.target_map:
                    acc_non_cash = sum(v for k, v in acc.target_map.items() if k != cash_asset_class_id)
                    acc_cash_pct = Decimal("100.00") - acc_non_cash
                else:
                    acc_cash_pct = cash_target_pct

                if acc_cash_pct < 0: acc_cash_pct = Decimal("0.00")

                acc_target_val = acc_total_val * (acc_cash_pct / Decimal("100.00"))
                at_agg_target_val += acc_target_val

                acc_variance = acc_current - acc_target_val

                # Formatting
                if mode == "percent":
                   c_disp = str(accounting_percent((acc_current/acc_total_val*100) if acc_total_val else 0, 1))
                   t_disp = str(accounting_percent((acc_target_val/acc_total_val*100) if acc_total_val else 0, 1))
                   v_disp = str(accounting_percent(((acc_current/acc_total_val*100) - (acc_target_val/acc_total_val*100)) if acc_total_val else 0, 1))
                else:
                   c_disp = str(accounting_amount(acc_current, 0))
                   t_disp = str(accounting_amount(acc_target_val, 0))
                   v_disp = str(accounting_amount(acc_variance, 0))

                accounts_data.append(TargetAccountColumnData(
                    account_id=acc.id,
                    account_name=acc.name,
                    account_type_id=at.id,
                    current=c_disp,
                    target=t_disp,
                    vtarget=v_disp,
                    current_raw=acc_current,
                    target_raw=acc_target_val,
                    vtarget_raw=acc_variance,
                    input_name="",
                    input_value="",
                    is_input=False
                ))

            # AT Display
            # Use aggregated target from accounts?
            # Or theoretical target?
            # Usage in asset row was: aggregated.
            # Let's use aggregated here too for consistency.
            at_display_target = at_agg_target_val
            at_variance = at_current - at_display_target

            if mode == "percent":
                at_current_pct = (at_current / at_total_val * 100) if at_total_val else Decimal("0.00")
                at_target_pct = (at_display_target / at_total_val * 100) if at_total_val else Decimal("0.00")

                c_disp = str(accounting_percent(at_current_pct, 1))
                w_disp = str(accounting_percent(at_target_pct, 1))
                v_disp = str(accounting_percent(at_current_pct - at_target_pct, 1))
            else:
                c_disp = str(accounting_amount(at_current, 0))
                w_disp = str(accounting_amount(at_display_target, 0))
                v_disp = str(accounting_amount(at_variance, 0))

            groups.append(TargetAccountTypeGroupData(
                account_type=TargetAccountTypeColumnData(
                    account_type_id=at.id,
                    code=at.code,
                    label=at.label,
                    current=c_disp,
                    target_input_name="",
                    target_input_value="",
                    weighted_target=w_disp,
                    vtarget=v_disp,
                    current_raw=at_current,
                    target_input_raw=Decimal(0),
                    weighted_target_raw=at_display_target,
                    vtarget_raw=at_variance,
                    is_input=False
                ),
                accounts=accounts_data
            ))

        # Portfolio Variance
        portfolio_variance = portfolio_current - portfolio_target

        if mode == "percent":
             p_current_pct = (portfolio_current / portfolio_total_value * 100) if portfolio_total_value else Decimal(0)
             p_target_pct = (portfolio_target / portfolio_total_value * 100) if portfolio_total_value else Decimal(0)

             p_c_disp = str(accounting_percent(p_current_pct, 1))
             p_t_disp = str(accounting_percent(p_target_pct, 1))
             p_v_disp = str(accounting_percent(p_current_pct - p_target_pct, 1))
        else:
             p_c_disp = str(accounting_amount(portfolio_current, 0))
             p_t_disp = str(accounting_amount(portfolio_target, 0))
             p_v_disp = str(accounting_amount(portfolio_variance, 0))

        return TargetAllocationTableRow(
            asset_class_id=cash_asset_class_id,
            asset_class_name="Cash",
            category_code="CASH",
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=False,
            is_cash=True,
            groups=groups,
            portfolio_current=p_c_disp,
            portfolio_target=p_t_disp,
            portfolio_vtarget=p_v_disp,
            row_css_class="table-info"
        )

    def _build_grand_total_row(
        self,
        *,
        grand_total: Decimal,
        at_grand_totals: dict[int, Decimal],
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
    ) -> TargetAllocationTableRow:
        # Grand Total Row
        groups = []

        for at in account_types:
            at_current = at_grand_totals.get(at.id, Decimal("0.00"))

            # Grand total target = current (variance 0)
            at_target = at_current
            Decimal("0.00")

            accounts_data = []
            for acc in getattr(at, "active_accounts", []):
                # We need acc current
                # Pass data? Or assume we can look it up?
                # We didn't pass account data.
                # But grand total logic implies we sum everything?
                # Actually, account.current_total_value IS the grand total for that account.
                acc_current = getattr(acc, "current_total_value", Decimal("0.00"))
                acc_target = acc_current

                # Formatting
                if mode == "percent":
                   # % of Account Total (100%)
                   c_disp = "100.0%"
                   t_disp = "100.0%"
                   v_disp = "0.0%"
                else:
                   c_disp = str(accounting_amount(acc_current, 0))
                   t_disp = str(accounting_amount(acc_target, 0))
                   v_disp = "0"

                accounts_data.append(TargetAccountColumnData(
                    account_id=acc.id,
                    account_name=acc.name,
                    account_type_id=at.id,
                    current=c_disp,
                    target=t_disp,
                    vtarget=v_disp,
                    current_raw=acc_current,
                    target_raw=acc_target,
                    vtarget_raw=Decimal(0),
                    input_name="",
                    input_value="",
                    is_input=False
                ))

            if mode == "percent":
                   c_disp = "100.0%"
                   w_disp = "100.0%"
                   v_disp = "0.0%"
            else:
                   c_disp = str(accounting_amount(at_current, 0))
                   w_disp = str(accounting_amount(at_target, 0))
                   v_disp = "0"

            groups.append(TargetAccountTypeGroupData(
                account_type=TargetAccountTypeColumnData(
                    account_type_id=at.id,
                    code=at.code,
                    label=at.label,
                    current=c_disp,
                    target_input_name="",
                    target_input_value="",
                    weighted_target=w_disp,
                    vtarget=v_disp,
                    current_raw=at_current,
                    target_input_raw=Decimal(0),
                    weighted_target_raw=at_target,
                    vtarget_raw=Decimal(0),
                    is_input=False
                ),
                accounts=accounts_data
            ))

        # Portfolio
        if mode == "percent":
             p_c_disp = "100.0%"
             p_t_disp = "100.0%"
             p_v_disp = "0.0%"
        else:
             p_c_disp = str(accounting_amount(grand_total, 0))
             p_t_disp = str(accounting_amount(grand_total, 0))
             p_v_disp = "0"

        return TargetAllocationTableRow(
            asset_class_id=0,
            asset_class_name="Total",
            category_code="",
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=True,
            is_cash=False,
            groups=groups,
            portfolio_current=p_c_disp,
            portfolio_target=p_t_disp,
            portfolio_vtarget=p_v_disp,
            row_css_class="table-dark fw-bold"
        )

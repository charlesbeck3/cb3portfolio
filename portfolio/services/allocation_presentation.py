"""
Presentation formatters for allocation DataFrames.

Converts raw numeric DataFrames from AllocationCalculationEngine
into display-ready dictionaries for Django templates.

DESIGN PHILOSOPHY:
- Calculation engine returns ONLY numeric values
- This module handles ALL formatting for display
- Templates receive ready-to-render dicts with formatted strings
"""

from decimal import Decimal
from typing import Any

import pandas as pd


class AllocationPresentationFormatter:
    """
    Format numeric allocation DataFrames for template display.

    Separates calculation logic (in engine) from presentation logic (here).
    """

    def format_presentation_rows(
        self,
        aggregated_data: dict[str, pd.DataFrame],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
        mode: str = "percent",
    ) -> list[dict[str, Any]]:
        """
        Format aggregated numeric DataFrames into display-ready rows.

        Args:
            aggregated_data: Dict from aggregate_presentation_levels() with:
                - 'assets': Asset-level data
                - 'category_subtotals': Category aggregations
                - 'group_totals': Group aggregations
                - 'grand_total': Portfolio total
            accounts_by_type: Account metadata for building nested structure
            target_strategies: Strategy assignments for display
            mode: 'percent' or 'dollar' for display format

        Returns:
            List of formatted row dicts ready for template rendering.
            Each row contains formatted strings for display.
        """
        rows: list[dict[str, Any]] = []

        df_assets = aggregated_data["assets"]
        df_subtotals = aggregated_data["category_subtotals"]
        df_group_totals = aggregated_data["group_totals"]
        df_grand_total = aggregated_data["grand_total"]

        if df_assets.empty:
            return rows

        # Process assets in hierarchical order
        for group_code in df_assets.index.get_level_values("group_code").unique():
            group_assets = df_assets.loc[group_code]

            # Handle single category in group
            if not isinstance(group_assets, pd.DataFrame):
                group_assets = pd.DataFrame([group_assets])

            for category_code in group_assets.index.get_level_values("category_code").unique():
                category_assets = group_assets.loc[category_code]

                # Handle single asset in category
                if not isinstance(category_assets, pd.DataFrame):
                    category_assets = pd.DataFrame([category_assets])

                # Format asset rows in this category
                for _idx, asset_row in category_assets.iterrows():
                    formatted_row = self._format_asset_row(
                        asset_row=asset_row,
                        accounts_by_type=accounts_by_type,
                        target_strategies=target_strategies,
                        mode=mode,
                    )
                    rows.append(formatted_row)

                # Add category subtotal if exists
                if not df_subtotals.empty and (group_code, category_code) in df_subtotals.index:
                    subtotal_row = df_subtotals.loc[(group_code, category_code)]
                    formatted_subtotal = self._format_subtotal_row(
                        subtotal_row=subtotal_row,
                        accounts_by_type=accounts_by_type,
                        mode=mode,
                        row_type="subtotal",
                    )
                    rows.append(formatted_subtotal)

            # Add group total if exists
            if not df_group_totals.empty and group_code in df_group_totals.index:
                group_row = df_group_totals.loc[group_code]
                formatted_group = self._format_subtotal_row(
                    subtotal_row=group_row,
                    accounts_by_type=accounts_by_type,
                    mode=mode,
                    row_type="group_total",
                )
                rows.append(formatted_group)

        # Add grand total
        if not df_grand_total.empty:
            grand_row = df_grand_total.iloc[0]
            formatted_grand = self._format_subtotal_row(
                subtotal_row=grand_row,
                accounts_by_type=accounts_by_type,
                mode=mode,
                row_type="grand_total",
            )
            rows.append(formatted_grand)

        return rows

    def _format_asset_row(
        self,
        asset_row: pd.Series,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Format a single asset row with all account types and accounts.

        Converts numeric values to formatted display strings.
        """
        # Metadata might be in columns or in index (if row came from iterrows on a MultiIndex)
        def get_val(key: str, default: Any = "") -> Any:
            if key in asset_row.index:
                return asset_row[key]
            return default

        # If this is a Series from iterrows, the name might be the index value
        # we need to be careful with MultiIndex vs single index
        ac_name = get_val("asset_class_name", asset_row.name if isinstance(asset_row.name, str) else "")

        row = {
            "row_type": "asset",
            "asset_class_id": int(get_val("asset_class_id", 0)),
            "asset_class_name": ac_name,
            "group_code": get_val("group_code"),
            "group_label": get_val("group_label"),
            "category_code": get_val("category_code"),
            "category_label": get_val("category_label"),
            "is_asset": True,
            "is_subtotal": False,
            "is_group_total": False,
            "is_grand_total": False,
            "is_cash": bool(asset_row.get("is_cash", False)),
            "css_class": "",
        }

        # Format portfolio values
        if mode == "percent":
            row["portfolio"] = {
                "current": self._format_value(asset_row["portfolio_current_pct"], mode),
                "target": self._format_value(asset_row["portfolio_target_pct"], mode),
                "variance": self._format_variance(asset_row["portfolio_variance_pct"], mode),
            }
        else:
            row["portfolio"] = {
                "current": self._format_value(asset_row["portfolio_current"], mode),
                "target": self._format_value(asset_row["portfolio_target"], mode),
                "variance": self._format_variance(asset_row["portfolio_variance"], mode),
            }

        # Format account type columns
        account_type_columns = []

        for type_id, type_accounts in sorted(accounts_by_type.items()):
            type_code = type_accounts[0]["type_code"]
            type_label = type_accounts[0]["type_label"]

            # Get values for this account type
            at_current = asset_row.get(f"{type_code}_current", 0.0)
            at_target_input = asset_row.get(f"{type_code}_target_input", None)
            at_weighted_target = asset_row.get(f"{type_code}_weighted_target", 0.0)
            at_variance = asset_row.get(f"{type_code}_variance", 0.0)

            # Format account columns
            account_columns = []
            for acc_meta in type_accounts:
                acc_name = acc_meta["name"]
                acc_id = acc_meta["id"]
                acc_prefix = f"{type_code}_{acc_name}"

                acc_current = asset_row.get(f"{acc_prefix}_current", 0.0)
                acc_target = asset_row.get(f"{acc_prefix}_target", 0.0)
                acc_variance = asset_row.get(f"{acc_prefix}_variance", 0.0)
                acc_target_pct = asset_row.get(f"{acc_prefix}_target_pct", 0.0)
                acc_current_pct = asset_row.get(f"{acc_prefix}_current_pct", 0.0)

                account_columns.append(
                    {
                        "id": acc_id,
                        "name": acc_name,
                        "current": self._format_value(
                            acc_current_pct if mode == "percent" else acc_current, mode
                        ),
                        "current_raw": float(acc_current),
                        "current_pct": float(acc_current_pct),
                        "target": self._format_value(
                            acc_target_pct if mode == "percent" else acc_target, mode
                        ),
                        "target_raw": float(acc_target),
                        "target_pct": float(acc_target_pct),
                        "variance": self._format_variance(
                            (acc_current_pct - acc_target_pct) if mode == "percent" else acc_variance,
                            mode,
                        ),
                        "variance_raw": float(acc_variance),
                        "variance_pct": float(acc_current_pct - acc_target_pct),
                        "allocation_strategy_id": target_strategies.get("acc_strategy_map", {}).get(
                            acc_id
                        ),
                    }
                )

            # Format account type values
            at_current_pct = asset_row.get(f"{type_code}_current_pct", 0.0)
            at_weighted_pct = asset_row.get(f"{type_code}_weighted_target_pct", 0.0)

            account_type_columns.append(
                {
                    "id": type_id,
                    "code": type_code,
                    "label": type_label,
                    "current": self._format_value(at_current, mode),
                    "current_raw": float(at_current),
                    "current_pct": float(at_current_pct),
                    "target_input": (
                        f"{at_target_input:.1f}%" if at_target_input is not None else ""
                    ),
                    "target_input_raw": at_target_input if at_target_input is not None else None,
                    "target_input_value": (
                        f"{at_target_input:.1f}%" if at_target_input is not None else ""
                    ),
                    "weighted_target": self._format_value(at_weighted_target, mode),
                    "weighted_target_raw": (
                        float(at_weighted_pct) if mode == "percent" else float(at_weighted_target)
                    ),
                    "weighted_target_pct": float(at_weighted_pct),
                    "variance": self._format_variance(at_variance, mode),
                    "variance_raw": (
                        float(at_current_pct - at_weighted_pct)
                        if mode == "percent"
                        else float(at_variance)
                    ),
                    "variance_pct": float(at_current_pct - at_weighted_pct),
                    "vtarget": self._format_variance(at_variance, mode),
                    "active_strategy_id": target_strategies.get("at_strategy_map", {}).get(type_id),
                    "active_accounts": account_columns,
                    "accounts": account_columns,
                }
            )

        row["account_types"] = account_type_columns

        return row

    def _format_subtotal_row(
        self,
        subtotal_row: pd.Series,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        mode: str,
        row_type: str,
    ) -> dict[str, Any]:
        """
        Format subtotal, group total, or grand total row.

        All three types use the same structure, just different metadata.
        """
        # Metadata might be in columns or in index
        def get_val(key: str, default: Any = "") -> Any:
            if key in subtotal_row.index:
                return subtotal_row[key]
            return default

        # Determine display name and CSS class
        if row_type == "grand_total":
            display_name = "Total"
            css_class = "grand-total"
        elif row_type == "group_total":
            display_name = f"{get_val('group_label')} Total"
            css_class = "group-total"
        else:  # subtotal
            display_name = f"{get_val('category_label')} Total"
            css_class = "subtotal"

        row = {
            "row_type": row_type,
            "asset_class_id": 0,
            "asset_class_name": display_name,
            "group_code": get_val("group_code"),
            "group_label": get_val("group_label"),
            "category_code": get_val("category_code"),
            "category_label": get_val("category_label"),
            "is_asset": False,
            "is_subtotal": row_type == "subtotal",
            "is_group_total": row_type == "group_total",
            "is_grand_total": row_type == "grand_total",
            "is_cash": False,
            "css_class": css_class,
        }

        # Format portfolio values
        if mode == "percent":
            row["portfolio"] = {
                "current": self._format_value(subtotal_row.get("portfolio_current_pct", 0.0), mode),
                "target": self._format_value(subtotal_row.get("portfolio_target_pct", 0.0), mode),
                "variance": self._format_variance(
                    subtotal_row.get("portfolio_variance_pct", 0.0), mode
                ),
            }
        else:
            row["portfolio"] = {
                "current": self._format_value(subtotal_row.get("portfolio_current", 0.0), mode),
                "target": self._format_value(subtotal_row.get("portfolio_target", 0.0), mode),
                "variance": self._format_variance(
                    subtotal_row.get("portfolio_variance", 0.0), mode
                ),
            }

        # Format account type columns
        account_type_columns = []

        for type_id, type_accounts in sorted(accounts_by_type.items()):
            type_code = type_accounts[0]["type_code"]
            type_label = type_accounts[0]["type_label"]

            at_current = subtotal_row.get(f"{type_code}_current", 0.0)
            at_weighted_target = subtotal_row.get(f"{type_code}_weighted_target", 0.0)
            at_variance = subtotal_row.get(f"{type_code}_variance", 0.0)
            at_current_pct = subtotal_row.get(f"{type_code}_current_pct", 0.0)
            at_weighted_pct = subtotal_row.get(f"{type_code}_weighted_target_pct", 0.0)

            # Format account columns
            account_columns = []
            for acc_meta in type_accounts:
                acc_name = acc_meta["name"]
                acc_id = acc_meta["id"]
                acc_prefix = f"{type_code}_{acc_name}"

                acc_current = subtotal_row.get(f"{acc_prefix}_current", 0.0)
                acc_current_pct = subtotal_row.get(f"{acc_prefix}_current_pct", 0.0)
                acc_target = subtotal_row.get(f"{acc_prefix}_target", 0.0)
                acc_target_pct = subtotal_row.get(f"{acc_prefix}_target_pct", 0.0)
                acc_variance = subtotal_row.get(f"{acc_prefix}_variance", 0.0)

                account_columns.append(
                    {
                        "id": acc_id,
                        "name": acc_name,
                        "current": self._format_value(
                            acc_current_pct if mode == "percent" else acc_current, mode
                        ),
                        "current_raw": float(acc_current),
                        "target": self._format_value(
                            acc_target_pct if mode == "percent" else acc_target, mode
                        ),
                        "target_raw": float(acc_target),
                        "variance": self._format_variance(
                            (acc_current_pct - acc_target_pct) if mode == "percent" else acc_variance,
                            mode,
                        ),
                        "variance_raw": float(acc_variance),
                    }
                )

            account_type_columns.append(
                {
                    "id": type_id,
                    "code": type_code,
                    "label": type_label,
                    "current": self._format_value(at_current, mode),
                    "current_raw": float(at_current),
                    "current_pct": float(at_current_pct),
                    "weighted_target": self._format_value(at_weighted_target, mode),
                    "weighted_target_raw": (
                        float(at_weighted_pct) if mode == "percent" else float(at_weighted_target)
                    ),
                    "weighted_target_pct": float(at_weighted_pct),
                    "variance": self._format_variance(at_variance, mode),
                    "variance_raw": (
                        float(at_current_pct - at_weighted_pct)
                        if mode == "percent"
                        else float(at_variance)
                    ),
                    "variance_pct": float(at_current_pct - at_weighted_pct),
                    "vtarget": self._format_variance(at_variance, mode),
                    "active_accounts": account_columns,
                    "accounts": account_columns,
                }
            )

        row["account_types"] = account_type_columns

        return row

    def _format_value(self, value: float, mode: str) -> str:
        """
        Format a numeric value for display.

        Args:
            value: Numeric value to format
            mode: 'percent' or 'dollar'

        Returns:
            Formatted string (e.g., "42.5%" or "$1,234")
        """
        if mode == "percent":
            return f"{value:.1f}%"
        else:
            return f"${value:,.0f}"

    def _format_variance(self, value: float, mode: str) -> str:
        """
        Format a variance value with appropriate sign.

        Args:
            value: Numeric variance value
            mode: 'percent' or 'dollar'

        Returns:
            Formatted string with sign (e.g., "+5.2%" or "($1,234)")
        """
        if mode == "percent":
            return f"{value:+.1f}%"
        else:
            # Use accounting format for dollars
            return self._format_money(Decimal(str(value)))

    def _format_money(self, val: Decimal) -> str:
        """
        Format decimal as money string: $1,234 or ($1,234).

        Negative values shown in parentheses (accounting format).
        """
        is_negative = val < 0
        abs_val = abs(val)
        s = f"${abs_val:,.0f}"
        return f"({s})" if is_negative else s

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

        REFACTORED: Eliminates iterrows() using vectorized formatting + to_dict('records').
        """
        df_assets = aggregated_data["assets"]
        df_subtotals = aggregated_data["category_subtotals"]
        df_group_totals = aggregated_data["group_totals"]
        df_grand_total = aggregated_data["grand_total"]

        if df_assets.empty:
            return []

        # Step 1: Pre-format all columns using vectorized operations
        df_assets, df_subtotals, df_group_totals, df_grand_total = self._preformat_all_columns(
            df_assets, df_subtotals, df_group_totals, df_grand_total, accounts_by_type, mode
        )

        # Step 2: Convert assets to dicts (using fast to_dict('records'))
        asset_rows = self._dataframe_rows_to_dicts(
            df_assets, accounts_by_type, target_strategies, mode
        )

        # Step 3: Convert aggregation rows to dicts
        subtotal_rows = (
            self._dataframe_rows_to_dicts(df_subtotals, accounts_by_type, target_strategies, mode)
            if not df_subtotals.empty
            else []
        )

        group_rows = (
            self._dataframe_rows_to_dicts(
                df_group_totals, accounts_by_type, target_strategies, mode
            )
            if not df_group_totals.empty
            else []
        )

        grand_rows = (
            self._dataframe_rows_to_dicts(df_grand_total, accounts_by_type, target_strategies, mode)
            if not df_grand_total.empty
            else []
        )

        # Step 4: Interleave rows in hierarchical order
        result = self._interleave_hierarchical_rows(
            asset_rows, subtotal_rows, group_rows, grand_rows
        )

        return result

    def _format_dataframe_columns(
        self,
        df: pd.DataFrame,
        col_prefix: str,
        mode: str,
    ) -> pd.DataFrame:
        """
        Format a set of numeric columns for display using vectorized operations.
        """
        # Format current
        curr_pct_col = f"{col_prefix}_current_pct"
        curr_col = f"{col_prefix}_current"
        if curr_pct_col in df.columns and mode == "percent":
            df[f"{col_prefix}_current_fmt"] = df[curr_pct_col].apply(lambda x: f"{x:.1f}%")
        elif curr_col in df.columns:
            df[f"{col_prefix}_current_fmt"] = df[curr_col].apply(lambda x: f"${x:,.0f}")

        # Format target
        tgt_pct_col = (
            f"{col_prefix}_target_pct"
            if f"{col_prefix}_target_pct" in df.columns
            else f"{col_prefix}_weighted_target_pct"
        )
        tgt_col = (
            f"{col_prefix}_target"
            if f"{col_prefix}_target" in df.columns
            else f"{col_prefix}_weighted_target"
        )

        if tgt_pct_col in df.columns and mode == "percent":
            df[f"{col_prefix}_target_fmt"] = df[tgt_pct_col].apply(lambda x: f"{x:.1f}%")
        elif tgt_col in df.columns:
            df[f"{col_prefix}_target_fmt"] = df[tgt_col].apply(lambda x: f"${x:,.0f}")

        # Format variance
        var_pct_col = f"{col_prefix}_variance_pct"
        var_col = f"{col_prefix}_variance"
        if var_pct_col in df.columns and mode == "percent":
            df[f"{col_prefix}_variance_fmt"] = df[var_pct_col].apply(lambda x: f"{x:+.1f}%")
        elif var_col in df.columns:
            df[f"{col_prefix}_variance_fmt"] = df[var_col].apply(
                lambda x: self._format_money(Decimal(str(x)))
            )

        return df

    def _preformat_all_columns(
        self,
        df_assets: pd.DataFrame,
        df_subtotals: pd.DataFrame,
        df_group_totals: pd.DataFrame,
        df_grand_total: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        mode: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Pre-format all numeric columns in all DataFrames using vectorized operations.
        """
        dfs = [df_assets, df_subtotals, df_group_totals, df_grand_total]

        # Format portfolio columns
        for i, df in enumerate(dfs):
            if not df.empty:
                dfs[i] = self._format_dataframe_columns(df, "portfolio", mode)

        # Format account type columns
        for _type_id, type_accounts in accounts_by_type.items():
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]

            for i, df in enumerate(dfs):
                if not df.empty:
                    dfs[i] = self._format_dataframe_columns(df, type_code, mode)

            # Format individual account columns
            for acc_meta in type_accounts:
                acc_name = acc_meta["name"]
                acc_prefix = f"{type_code}_{acc_name}"

                for i, df in enumerate(dfs):
                    if not df.empty:
                        dfs[i] = self._format_dataframe_columns(df, acc_prefix, mode)

        return tuple(dfs)

    def _dataframe_rows_to_dicts(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
        mode: str,
    ) -> list[dict[str, Any]]:
        """
        Convert formatted DataFrame rows to list of dicts for template.
        """
        df_reset = df.reset_index()
        rows = df_reset.to_dict("records")

        formatted_rows = []
        for row in rows:
            formatted_row = self._build_row_dict_from_formatted_data(
                row, accounts_by_type, target_strategies, mode
            )
            formatted_rows.append(formatted_row)

        return formatted_rows

    def _build_row_dict_from_formatted_data(
        self,
        row: dict[str, Any],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Build final row dict from pre-formatted row data.
        """
        row_type = row.get("row_type", "asset")
        asset_class_name = row.get("asset_class_name", "")
        if not asset_class_name:
            if row_type == "grand_total":
                asset_class_name = "Total"
            elif row_type == "group_total":
                asset_class_name = f"{row.get('group_label', '')} Total"
            elif row_type == "subtotal":
                asset_class_name = f"{row.get('category_label', '')} Total"

        result = {
            "row_type": row_type,
            "asset_class_id": int(row.get("asset_class_id", 0)),
            "asset_class_name": asset_class_name,
            "group_code": row.get("group_code", ""),
            "group_label": row.get("group_label", ""),
            "category_code": row.get("category_code", ""),
            "category_label": row.get("category_label", ""),
            "is_asset": row_type == "asset",
            "is_subtotal": row_type == "subtotal",
            "is_group_total": row_type == "group_total",
            "is_grand_total": row_type == "grand_total",
            "is_cash": bool(row.get("is_cash", False)),
            "css_class": self._get_css_class(row_type),
        }

        result["portfolio"] = {
            "current": row.get("portfolio_current_fmt", ""),
            "target": row.get("portfolio_target_fmt", ""),
            "variance": row.get("portfolio_variance_fmt", ""),
        }

        account_type_columns = []
        for type_id, type_accounts in sorted(accounts_by_type.items()):
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]
            type_label = type_accounts[0]["type_label"]

            account_columns = []
            for acc_meta in type_accounts:
                acc_prefix = f"{type_code}_{acc_meta['name']}"
                account_columns.append(
                    {
                        "id": acc_meta["id"],
                        "name": acc_meta["name"],
                        "current": row.get(f"{acc_prefix}_current_fmt", ""),
                        "current_raw": float(row.get(f"{acc_prefix}_current", 0.0)),
                        "current_pct": float(row.get(f"{acc_prefix}_current_pct", 0.0)),
                        "target": row.get(f"{acc_prefix}_target_fmt", ""),
                        "target_raw": float(row.get(f"{acc_prefix}_target", 0.0)),
                        "target_pct": float(row.get(f"{acc_prefix}_target_pct", 0.0)),
                        "variance": row.get(f"{acc_prefix}_variance_fmt", ""),
                        "variance_raw": float(row.get(f"{acc_prefix}_variance", 0.0)),
                        "variance_pct": float(
                            row.get(f"{acc_prefix}_current_pct", 0.0)
                            - row.get(f"{acc_prefix}_target_pct", 0.0)
                        ),
                        "allocation_strategy_id": target_strategies.get("acc_strategy_map", {}).get(
                            acc_meta["id"]
                        ),
                    }
                )

            at_target_input = row.get(f"{type_code}_target_input")
            account_type_columns.append(
                {
                    "id": type_id,
                    "code": type_code,
                    "label": type_label,
                    "current": row.get(f"{type_code}_current_fmt", ""),
                    "current_raw": float(row.get(f"{type_code}_current", 0.0)),
                    "current_pct": float(row.get(f"{type_code}_current_pct", 0.0)),
                    "target_input": (
                        f"{at_target_input:.1f}%" if at_target_input is not None else ""
                    ),
                    "target_input_raw": at_target_input,
                    "target_input_value": (
                        f"{at_target_input:.1f}%" if at_target_input is not None else ""
                    ),
                    "weighted_target": row.get(f"{type_code}_target_fmt", ""),
                    "weighted_target_raw": float(row.get(f"{type_code}_weighted_target", 0.0)),
                    "weighted_target_pct": float(row.get(f"{type_code}_weighted_target_pct", 0.0)),
                    "variance": row.get(f"{type_code}_variance_fmt", ""),
                    "variance_raw": float(row.get(f"{type_code}_variance", 0.0)),
                    "variance_pct": float(row.get(f"{type_code}_variance_pct", 0.0)),
                    "vtarget": (
                        f"{row.get(f'{type_code}_variance_pct', 0.0):+.1f}%"
                        if mode == "percent"
                        else row.get(f"{type_code}_variance_fmt", "")
                    ),
                    "active_strategy_id": target_strategies.get("at_strategy_map", {}).get(type_id),
                    "active_accounts": account_columns,
                    "accounts": account_columns,
                }
            )

        result["account_types"] = account_type_columns
        return result

    def _interleave_hierarchical_rows(
        self,
        asset_rows: list[dict[str, Any]],
        subtotal_rows: list[dict[str, Any]],
        group_rows: list[dict[str, Any]],
        grand_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Interleave asset/subtotal/group/grand rows in hierarchical order.
        """
        subtotals_by_key = {(r["group_code"], r["category_code"]): r for r in subtotal_rows}
        groups_by_key = {r["group_code"]: r for r in group_rows}

        from collections import defaultdict

        grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for row in asset_rows:
            grouped[row["group_code"]][row["category_code"]].append(row)

        result = []
        for group_code in grouped:
            cat_dict = grouped[group_code]
            for category_code in cat_dict:
                result.extend(cat_dict[category_code])
                if (group_code, category_code) in subtotals_by_key:
                    result.append(subtotals_by_key[(group_code, category_code)])
            if group_code in groups_by_key:
                result.append(groups_by_key[group_code])

        result.extend(grand_rows)
        return result

    def _get_css_class(self, row_type: str) -> str:
        """Get CSS class for row type."""
        css_map = {
            "asset": "",
            "subtotal": "subtotal",
            "group_total": "group-total",
            "grand_total": "grand-total",
        }
        return css_map.get(row_type, "")

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

    def format_holdings_rows(
        self,
        holdings_df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """
        Format holdings DataFrame into display-ready rows with aggregations.

        Follows the same pattern as format_presentation_rows() for consistency.
        Includes individual holdings, category subtotals, group totals, and grand total.

        Args:
            holdings_df: DataFrame from calculate_holdings_with_targets()

        Returns:
            List of display-ready dicts with formatted strings and raw values.
            Each dict has row_type: 'holding', 'subtotal', 'group_total', or 'grand_total'
        """
        if holdings_df.empty:
            return []

        # Step 1: Pre-format all numeric columns
        df = self._format_holdings_columns(holdings_df)

        # Step 2: Build individual holding rows
        holding_rows = self._holdings_to_dicts(df)

        # Step 3: Calculate aggregations
        subtotal_rows = self._calculate_holdings_subtotals(df)
        group_rows = self._calculate_holdings_group_totals(df)
        grand_row = self._calculate_holdings_grand_total(df)

        # Step 4: Interleave hierarchically
        result = self._interleave_holdings_hierarchical(
            holding_rows, subtotal_rows, group_rows, grand_row
        )

        return result

    def _format_holdings_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Vectorized formatting for all holdings numeric columns.

        Adds *_display columns for formatted strings while preserving raw numeric values.
        """
        formatted = df.copy()

        # Format price (always 2 decimals)
        formatted["price_display"] = formatted["Price"].apply(lambda x: f"${x:,.2f}")

        # Format shares (4 decimals for holdings, 2 for targets)
        formatted["shares_display"] = formatted["Shares"].apply(lambda x: f"{x:,.4f}")
        formatted["target_shares_display"] = formatted["Target_Shares"].apply(lambda x: f"{x:,.2f}")
        formatted["shares_variance_display"] = formatted["Shares_Variance"].apply(
            lambda x: f"{x:+,.2f}" if abs(x) > 0.01 else "—"
        )

        # Format values (no decimals, rounded to dollar)
        formatted["value_display"] = formatted["Value"].apply(lambda x: f"${x:,.0f}")
        formatted["target_value_display"] = formatted["Target_Value"].apply(lambda x: f"${x:,.0f}")
        formatted["value_variance_display"] = formatted["Value_Variance"].apply(
            lambda x: f"${x:+,.0f}" if abs(x) > 0.5 else "—"
        )

        # Format allocations (2 decimals)
        formatted["allocation_display"] = formatted["Allocation_Pct"].apply(lambda x: f"{x:.2f}%")
        formatted["target_allocation_display"] = formatted["Target_Allocation_Pct"].apply(
            lambda x: f"{x:.2f}%"
        )
        formatted["allocation_variance_display"] = formatted["Allocation_Variance_Pct"].apply(
            lambda x: f"{x:+.2f}%" if abs(x) > 0.01 else "—"
        )

        return formatted

    def _holdings_to_dicts(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Convert holdings DataFrame rows to display dictionaries.

        No custom dataclass needed - simple dicts match template expectations.
        """
        rows = []

        for _, row in df.iterrows():
            # Build parent_id for collapse functionality
            parent_id = f"cat-{row['Category_Code']}"

            rows.append({
                "row_type": "holding",
                "ticker": row["Ticker"],
                "security_name": row["Security_Name"],
                "asset_class": row["Asset_Class"],
                "asset_category": row["Asset_Category"],
                "asset_group": row["Asset_Group"],
                "group_code": row["Group_Code"],
                "category_code": row["Category_Code"],

                # Display values (formatted strings)
                "price": row["price_display"],
                "shares": row["shares_display"],
                "target_shares": row["target_shares_display"],
                "shares_variance": row["shares_variance_display"],
                "value": row["value_display"],
                "target_value": row["target_value_display"],
                "value_variance": row["value_variance_display"],
                "allocation": row["allocation_display"],
                "target_allocation": row["target_allocation_display"],
                "allocation_variance": row["allocation_variance_display"],

                # Raw values (for sorting/calculations in template if needed)
                "price_raw": row["Price"],
                "shares_raw": row["Shares"],
                "value_raw": row["Value"],
                "allocation_raw": row["Allocation_Pct"],
                "variance_raw": row["Value_Variance"],

                # UI metadata
                "is_holding": True,
                "is_subtotal": False,
                "is_group_total": False,
                "is_grand_total": False,
                "parent_id": parent_id,
                "row_class": f"{parent_id}-rows collapse show",
            })

        return rows

    def _calculate_holdings_subtotals(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Calculate category subtotals using pandas groupby.

        Returns formatted subtotal rows for each asset category.
        """
        if df.empty:
            return []

        # Group by asset category
        grouped = df.groupby(["Group_Code", "Category_Code", "Asset_Category"], sort=False).agg({
            "Value": "sum",
            "Target_Value": "sum",
            "Allocation_Pct": "sum",
            "Target_Allocation_Pct": "sum",
        }).reset_index()

        # Filter out single-holding categories (subtotal would be redundant)
        category_counts = df.groupby(["Group_Code", "Category_Code"]).size()
        multi_holding_categories = category_counts[category_counts > 1].index
        grouped = grouped[grouped.set_index(["Group_Code", "Category_Code"]).index.isin(multi_holding_categories)]

        if grouped.empty:
            return []

        # Calculate variances
        grouped["Value_Variance"] = grouped["Value"] - grouped["Target_Value"]
        grouped["Allocation_Variance"] = grouped["Allocation_Pct"] - grouped["Target_Allocation_Pct"]

        rows = []
        for _, row in grouped.iterrows():
            category_id = f"cat-{row['Category_Code']}"
            parent_id = f"grp-{row['Group_Code']}"

            rows.append({
                "row_type": "subtotal",
                "name": f"{row['Asset_Category']} Total",
                "category_code": row["Category_Code"],
                "group_code": row["Group_Code"],

                # Formatted display values
                "value": f"${row['Value']:,.0f}",
                "target_value": f"${row['Target_Value']:,.0f}",
                "value_variance": (
                    f"${row['Value_Variance']:+,.0f}"
                    if abs(row['Value_Variance']) > 0.5
                    else "—"
                ),
                "allocation": f"{row['Allocation_Pct']:.2f}%",
                "target_allocation": f"{row['Target_Allocation_Pct']:.2f}%",
                "allocation_variance": (
                    f"{row['Allocation_Variance']:+.2f}%"
                    if abs(row['Allocation_Variance']) > 0.01
                    else "—"
                ),

                # Raw values
                "value_raw": row["Value"],
                "variance_raw": row["Value_Variance"],

                # UI metadata
                "is_holding": False,
                "is_subtotal": True,
                "is_group_total": False,
                "is_grand_total": False,
                "row_id": category_id,
                "parent_id": parent_id,
                "row_class": f"table-secondary fw-bold {parent_id}-rows collapse show",
            })

        return rows

    def _calculate_holdings_group_totals(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Calculate asset group totals using pandas groupby.

        Returns formatted group total rows for each asset group (e.g., Equities, Fixed Income).
        """
        if df.empty:
            return []

        # Group by asset group
        grouped = df.groupby(["Group_Code", "Asset_Group"], sort=False).agg({
            "Value": "sum",
            "Target_Value": "sum",
            "Allocation_Pct": "sum",
            "Target_Allocation_Pct": "sum",
        }).reset_index()

        # Filter out single-category groups (total would be redundant)
        group_counts = df.groupby("Group_Code")["Category_Code"].nunique()
        multi_category_groups = group_counts[group_counts > 1].index
        grouped = grouped[grouped["Group_Code"].isin(multi_category_groups)]

        if grouped.empty:
            return []

        # Calculate variances
        grouped["Value_Variance"] = grouped["Value"] - grouped["Target_Value"]
        grouped["Allocation_Variance"] = grouped["Allocation_Pct"] - grouped["Target_Allocation_Pct"]

        rows = []
        for _, row in grouped.iterrows():
            group_id = f"grp-{row['Group_Code']}"

            rows.append({
                "row_type": "group_total",
                "name": f"{row['Asset_Group']} Total",
                "group_code": row["Group_Code"],

                # Formatted display values
                "value": f"${row['Value']:,.0f}",
                "target_value": f"${row['Target_Value']:,.0f}",
                "value_variance": (
                    f"${row['Value_Variance']:+,.0f}"
                    if abs(row['Value_Variance']) > 0.5
                    else "—"
                ),
                "allocation": f"{row['Allocation_Pct']:.2f}%",
                "target_allocation": f"{row['Target_Allocation_Pct']:.2f}%",
                "allocation_variance": (
                    f"{row['Allocation_Variance']:+.2f}%"
                    if abs(row['Allocation_Variance']) > 0.01
                    else "—"
                ),

                # Raw values
                "value_raw": row["Value"],
                "variance_raw": row["Value_Variance"],

                # UI metadata
                "is_holding": False,
                "is_subtotal": False,
                "is_group_total": True,
                "is_grand_total": False,
                "row_id": group_id,
                "parent_id": "",
                "row_class": "table-primary fw-bold border-top group-toggle",
            })

        return rows

    def _calculate_holdings_grand_total(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Calculate grand total across all holdings.

        Returns a single grand total row.
        """
        if df.empty:
            return []

        total_value = df["Value"].sum()
        total_target = df["Target_Value"].sum()
        total_variance = total_value - total_target

        # Allocations are always 100% for grand total
        total_alloc = 100.0
        total_target_alloc = 100.0

        return [{
            "row_type": "grand_total",
            "name": "Grand Total",

            # Formatted display values
            "value": f"${total_value:,.0f}",
            "target_value": f"${total_target:,.0f}",
            "value_variance": (
                f"${total_variance:+,.0f}"
                if abs(total_variance) > 0.5
                else "—"
            ),
            "allocation": f"{total_alloc:.2f}%",
            "target_allocation": f"{total_target_alloc:.2f}%",
            "allocation_variance": "—",

            # Raw values
            "value_raw": total_value,
            "variance_raw": total_variance,

            # UI metadata
            "is_holding": False,
            "is_subtotal": False,
            "is_group_total": False,
            "is_grand_total": True,
            "row_class": "table-dark fw-bold border-top-3",
        }]

    def _interleave_holdings_hierarchical(
        self,
        holding_rows: list[dict[str, Any]],
        subtotal_rows: list[dict[str, Any]],
        group_rows: list[dict[str, Any]],
        grand_row: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Interleave holdings, subtotals, group totals, and grand total in display order.

        Order: Holdings → Category Subtotals → Group Totals → Grand Total
        Grouped by: Asset Group → Asset Category → Individual Holdings
        """
        result = []

        # Build lookup maps for efficient access
        subtotals_by_category = {
            row["category_code"]: row
            for row in subtotal_rows
        }
        groups_by_code = {
            row["group_code"]: row
            for row in group_rows
        }

        # Group holdings by group_code and category_code
        from collections import defaultdict
        holdings_by_group: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

        for holding in holding_rows:
            holdings_by_group[holding["group_code"]][holding["category_code"]].append(holding)

        # Iterate through groups
        for group_code in sorted(holdings_by_group.keys()):
            categories = holdings_by_group[group_code]

            # Add holdings for each category
            for category_code in sorted(categories.keys()):
                holdings = categories[category_code]
                result.extend(holdings)

                # Add category subtotal if exists
                if category_code in subtotals_by_category:
                    result.append(subtotals_by_category[category_code])

            # Add group total if exists
            if group_code in groups_by_code:
                result.append(groups_by_code[group_code])

        # Add grand total at the end
        result.extend(grand_row)

        return result

"""
Presentation formatters for allocation DataFrames.

Converts raw numeric DataFrames from AllocationCalculationEngine
into display-ready dictionaries for Django templates.

DESIGN PHILOSOPHY:
- Calculation engine returns ONLY numeric values
- This module handles ALL formatting for display
- Templates receive ready-to-render dicts with formatted strings
"""

from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class AllocationPresentationFormatter:
    """
    Transform allocation DataFrames into template-ready dict structures.

    Converts pandas DataFrames to nested dictionaries with raw numeric values.
    Templates handle display formatting using |money, |percent, |number filters.

    Design Philosophy:
    - Engine: Calculations → numeric DataFrames
    - Formatter: Structure transformation → nested dicts
    - Template: Display formatting → formatted strings
    """

    def format_presentation_rows(
        self,
        aggregated_data: dict[str, pd.DataFrame],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
    ) -> list[dict[str, Any]]:
        logger.info("formatting_presentation_rows")
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

        # Step 1: Convert assets to dicts (using fast to_dict('records'))
        asset_rows = self._dataframe_rows_to_dicts(df_assets, accounts_by_type, target_strategies)

        # Step 2: Convert aggregation rows to dicts
        subtotal_rows = (
            self._dataframe_rows_to_dicts(df_subtotals, accounts_by_type, target_strategies)
            if not df_subtotals.empty
            else []
        )

        group_rows = (
            self._dataframe_rows_to_dicts(df_group_totals, accounts_by_type, target_strategies)
            if not df_group_totals.empty
            else []
        )

        grand_rows = (
            self._dataframe_rows_to_dicts(df_grand_total, accounts_by_type, target_strategies)
            if not df_grand_total.empty
            else []
        )

        # Step 3: Interleave rows in hierarchical order
        result = self._interleave_hierarchical_rows(
            asset_rows, subtotal_rows, group_rows, grand_rows
        )

        return result

    def _dataframe_rows_to_dicts(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Convert DataFrame rows to list of dicts for template.
        """
        df_reset = df.reset_index()
        rows = df_reset.to_dict("records")

        formatted_rows = []
        for row in rows:
            formatted_row = self._build_row_dict_from_formatted_data(
                row, accounts_by_type, target_strategies
            )
            formatted_rows.append(formatted_row)

        return formatted_rows

    def _build_row_dict_from_formatted_data(
        self,
        row: dict[str, Any],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
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
        }

        result["portfolio"] = {
            "actual": float(row.get("portfolio_actual", 0.0)),
            "actual_pct": float(row.get("portfolio_actual_pct", 0.0)),
            "effective": float(row.get("portfolio_effective", 0.0)),
            "effective_pct": float(row.get("portfolio_effective_pct", 0.0)),
            "effective_variance": float(row.get("portfolio_effective_variance", 0.0)),
            "effective_variance_pct": float(row.get("portfolio_effective_variance_pct", 0.0)),
            # Policy variance (vs explicit target)
            "policy_variance": float(row.get("portfolio_policy_variance", 0.0)),
            "policy_variance_pct": float(row.get("portfolio_policy_variance_pct", 0.0)),
            # Explicit target for reference if needed
            "explicit_target": float(row.get("portfolio_explicit_target", 0.0)),
            "explicit_target_pct": float(row.get("portfolio_explicit_target_pct", 0.0)),
        }

        account_type_columns = []
        for type_id, type_accounts in accounts_by_type.items():
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
                        "actual": float(row.get(f"{acc_prefix}_actual", 0.0)),
                        "actual_pct": float(row.get(f"{acc_prefix}_actual_pct", 0.0)),
                        "policy": float(row.get(f"{acc_prefix}_policy", 0.0)),
                        "policy_pct": float(row.get(f"{acc_prefix}_policy_pct", 0.0)),
                        "policy_variance": float(row.get(f"{acc_prefix}_policy_variance", 0.0)),
                        "policy_variance_pct": float(
                            row.get(f"{acc_prefix}_actual_pct", 0.0)
                            - row.get(f"{acc_prefix}_policy_pct", 0.0)
                        ),
                        "allocation_strategy_id": target_strategies.get("acc_strategy_map", {}).get(
                            acc_meta["id"]
                        ),
                    }
                )

            account_type_columns.append(
                {
                    "id": type_id,
                    "code": type_code,
                    "label": type_label,
                    "actual": float(row.get(f"{type_code}_actual", 0.0)),
                    "actual_pct": float(row.get(f"{type_code}_actual_pct", 0.0)),
                    "policy": float(row.get(f"{type_code}_policy", 0.0)),
                    "policy_pct": float(row.get(f"{type_code}_policy_pct", 0.0)),
                    "effective": float(row.get(f"{type_code}_effective", 0.0)),
                    "effective_pct": float(row.get(f"{type_code}_effective_pct", 0.0)),
                    "policy_variance": float(row.get(f"{type_code}_policy_variance", 0.0)),
                    "policy_variance_pct": float(row.get(f"{type_code}_policy_variance_pct", 0.0)),
                    "effective_variance": float(row.get(f"{type_code}_effective_variance", 0.0)),
                    "effective_variance_pct": float(
                        row.get(f"{type_code}_effective_variance_pct", 0.0)
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
            List of display-ready dicts with raw values.
            Each dict has row_type: 'holding', 'subtotal', 'group_total', or 'grand_total'
        """
        if holdings_df.empty:
            return []

        # Step 1: Build individual holding rows
        holding_rows = self._holdings_to_dicts(holdings_df)

        # Step 2: Calculate aggregations
        subtotal_rows = self._calculate_holdings_subtotals(holdings_df)
        group_rows = self._calculate_holdings_group_totals(holdings_df)
        grand_row = self._calculate_holdings_grand_total(holdings_df)

        # Step 3: Interleave hierarchically
        result = self._interleave_holdings_hierarchical(
            holding_rows, subtotal_rows, group_rows, grand_row
        )

        return result

    def _holdings_to_dicts(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Convert holdings DataFrame rows to display dictionaries.

        No custom dataclass needed - simple dicts match template expectations.
        """
        rows = []

        for _, row in df.iterrows():
            # Build parent_id for collapse functionality
            parent_id = f"cat-{row['Category_Code']}"

            rows.append(
                {
                    "row_type": "holding",
                    "ticker": row["Ticker"],
                    "security_name": row["Security_Name"],
                    "asset_class": row["Asset_Class"],
                    "asset_category": row["Asset_Category"],
                    "asset_group": row["Asset_Group"],
                    "group_code": row["Group_Code"],
                    "category_code": row["Category_Code"],
                    # Raw Values
                    "price": float(row["Price"]),
                    "shares": float(row["Shares"]),
                    "target_shares": float(row["Target_Shares"]),
                    "shares_variance": float(row["Shares_Variance"]),
                    "value": float(row["Value"]),
                    "target_value": float(row["Target_Value"]),
                    "value_variance": float(row["Value_Variance"]),
                    "allocation": float(row["Allocation_Pct"]),
                    "target_allocation": float(row["Target_Allocation_Pct"]),
                    "allocation_variance": float(row["Allocation_Variance_Pct"]),
                    # UI metadata
                    "is_holding": True,
                    "is_subtotal": False,
                    "is_group_total": False,
                    "is_grand_total": False,
                    "parent_id": parent_id,
                    "row_class": f"{parent_id}-rows collapse show",
                }
            )

        return rows

    def _calculate_holdings_subtotals(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Calculate category subtotals using pandas groupby.

        Returns formatted subtotal rows for each asset category.
        """
        if df.empty:
            return []

        # Group by asset category
        grouped = (
            df.groupby(["Group_Code", "Category_Code", "Asset_Category"], sort=False)
            .agg(
                {
                    "Value": "sum",
                    "Target_Value": "sum",
                    "Allocation_Pct": "sum",
                    "Target_Allocation_Pct": "sum",
                }
            )
            .reset_index()
        )

        # Filter out single-holding categories (subtotal would be redundant)
        category_counts = df.groupby(["Group_Code", "Category_Code"]).size()
        multi_holding_categories = category_counts[category_counts > 1].index
        grouped = grouped[
            grouped.set_index(["Group_Code", "Category_Code"]).index.isin(multi_holding_categories)
        ]

        if grouped.empty:
            return []

        # Calculate variances
        grouped["Value_Variance"] = grouped["Value"] - grouped["Target_Value"]
        grouped["Allocation_Variance"] = (
            grouped["Allocation_Pct"] - grouped["Target_Allocation_Pct"]
        )

        rows = []
        for _, row in grouped.iterrows():
            category_id = f"cat-{row['Category_Code']}"
            parent_id = f"grp-{row['Group_Code']}"

            rows.append(
                {
                    "row_type": "subtotal",
                    "name": f"{row['Asset_Category']} Total",
                    "category_code": row["Category_Code"],
                    "group_code": row["Group_Code"],
                    # Raw values
                    "value": float(row["Value"]),
                    "target_value": float(row["Target_Value"]),
                    "value_variance": float(row["Value_Variance"]),
                    "allocation": float(row["Allocation_Pct"]),
                    "target_allocation": float(row["Target_Allocation_Pct"]),
                    "allocation_variance": float(row["Allocation_Variance"]),
                    # UI metadata
                    "is_holding": False,
                    "is_subtotal": True,
                    "is_group_total": False,
                    "is_grand_total": False,
                    "row_id": category_id,
                    "parent_id": parent_id,
                    "row_class": f"table-secondary fw-bold {parent_id}-rows collapse show",
                }
            )

        return rows

    def _calculate_holdings_group_totals(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Calculate asset group totals using pandas groupby.

        Returns formatted group total rows for each asset group (e.g., Equities, Fixed Income).
        """
        if df.empty:
            return []

        # Group by asset group
        grouped = (
            df.groupby(["Group_Code", "Asset_Group"], sort=False)
            .agg(
                {
                    "Value": "sum",
                    "Target_Value": "sum",
                    "Allocation_Pct": "sum",
                    "Target_Allocation_Pct": "sum",
                }
            )
            .reset_index()
        )

        # Filter out single-category groups (total would be redundant)
        group_counts = df.groupby("Group_Code")["Category_Code"].nunique()
        multi_category_groups = group_counts[group_counts > 1].index
        grouped = grouped[grouped["Group_Code"].isin(multi_category_groups)]

        if grouped.empty:
            return []

        # Calculate variances
        grouped["Value_Variance"] = grouped["Value"] - grouped["Target_Value"]
        grouped["Allocation_Variance"] = (
            grouped["Allocation_Pct"] - grouped["Target_Allocation_Pct"]
        )

        rows = []
        for _, row in grouped.iterrows():
            group_id = f"grp-{row['Group_Code']}"

            rows.append(
                {
                    "row_type": "group_total",
                    "name": f"{row['Asset_Group']} Total",
                    "group_code": row["Group_Code"],
                    # Raw values
                    "value": float(row["Value"]),
                    "target_value": float(row["Target_Value"]),
                    "value_variance": float(row["Value_Variance"]),
                    "allocation": float(row["Allocation_Pct"]),
                    "target_allocation": float(row["Target_Allocation_Pct"]),
                    "allocation_variance": float(row["Allocation_Variance"]),
                    # UI metadata
                    "is_holding": False,
                    "is_subtotal": False,
                    "is_group_total": True,
                    "is_grand_total": False,
                    "row_id": group_id,
                    "parent_id": "",
                    "row_class": "table-primary fw-bold border-top group-toggle",
                }
            )

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

        return [
            {
                "row_type": "grand_total",
                "name": "Grand Total",
                # Raw values
                "value": float(total_value),
                "target_value": float(total_target),
                "value_variance": float(total_variance),
                "allocation": float(total_alloc),
                "target_allocation": float(total_target_alloc),
                "allocation_variance": 0.0,
                # UI metadata
                "is_holding": False,
                "is_subtotal": False,
                "is_group_total": False,
                "is_grand_total": True,
                "row_class": "table-dark fw-bold border-top-3",
            }
        ]

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
        subtotals_by_category = {row["category_code"]: row for row in subtotal_rows}
        groups_by_code = {row["group_code"]: row for row in group_rows}

        # Group holdings by group_code and category_code
        from collections import defaultdict

        holdings_by_group: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for holding in holding_rows:
            holdings_by_group[holding["group_code"]][holding["category_code"]].append(holding)

        # Iterate through groups
        # Iterate through groups
        for group_code in holdings_by_group:
            categories = holdings_by_group[group_code]

            # Add holdings for each category
            for category_code in categories:
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

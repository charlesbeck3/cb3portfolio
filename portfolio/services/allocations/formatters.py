"""Formatting layer for converting DataFrames to template-ready dicts."""

from typing import Any

import pandas as pd


class AllocationFormatter:
    """Format DataFrames into template-ready dictionary structures."""

    def to_presentation_rows(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Transform presentation DataFrame to template-ready rows.

        Returns list of dicts with raw numeric values.
        Templates handle formatting via |money, |percent filters.

        Args:
            df: Presentation DataFrame from calculator
            accounts_by_type: Metadata about accounts grouped by type
            target_strategies: Strategy assignments map for dropdowns

        Returns:
            List of row dicts ready for template rendering
        """
        if df.empty:
            return []

        target_strategies = target_strategies or {}
        at_strategy_map = target_strategies.get("at_strategy_map", {})
        acc_strategy_map = target_strategies.get("acc_strategy_map", {})

        rows = []

        for _idx, row in df.iterrows():
            # Base row structure
            row_dict = {
                "asset_class_name": row["asset_class_name"],
                "asset_class_id": int(row["asset_class_id"]),
                "group_code": row.get("group_code", ""),
                "group_label": row.get("group_label", ""),
                "category_code": row.get("category_code", ""),
                "category_label": row.get("category_label", ""),
                "is_cash": bool(row.get("is_cash", False)),
                "hierarchy_level": int(row.get("hierarchy_level", 999)),
                # Portfolio metrics (raw numerics only)
                "portfolio": {
                    "actual": float(row.get("portfolio_actual", 0.0)),
                    "actual_pct": float(row.get("portfolio_actual_pct", 0.0)),
                    "effective": float(row.get("portfolio_effective", 0.0)),
                    "effective_pct": float(row.get("portfolio_effective_pct", 0.0)),
                    # Policy target = portfolio's allocation_strategy target
                    "explicit_target": float(row.get("portfolio_policy", 0.0)),
                    "explicit_target_pct": float(row.get("portfolio_policy_pct", 0.0)),
                    # Effective variance = actual - effective (for rebalancing)
                    "effective_variance": float(row.get("portfolio_variance", 0.0)),
                    "effective_variance_pct": float(row.get("portfolio_variance_pct", 0.0)),
                    # Policy variance = actual - policy (for policy adherence)
                    "policy_variance": float(row.get("portfolio_policy_variance", 0.0)),
                    "policy_variance_pct": float(row.get("portfolio_policy_variance_pct", 0.0)),
                },
            }

            # Add account type data
            account_types = []
            for type_id, accounts in accounts_by_type.items():
                if not accounts:
                    continue

                # Get type_code from first account in this type
                type_code = accounts[0].get("type_code", "")
                type_label = accounts[0].get("type_label", type_code)

                # Collect accounts for this type to populate active_accounts
                type_accounts_data = []
                for account_meta in accounts:
                    acc_id = account_meta["id"]
                    acc_prefix = f"{type_code}_{account_meta['name']}"

                    acc_data = {
                        "id": acc_id,
                        "name": account_meta["name"],
                        "actual": float(row.get(f"{acc_prefix}_actual", 0.0)),
                        "actual_pct": float(row.get(f"{acc_prefix}_actual_pct", 0.0)),
                        "policy": float(row.get(f"{acc_prefix}_policy", 0.0)),
                        "policy_pct": float(row.get(f"{acc_prefix}_policy_pct", 0.0)),
                        "policy_variance": float(row.get(f"{acc_prefix}_policy_variance", 0.0)),
                        "policy_variance_pct": float(
                            row.get(f"{acc_prefix}_policy_variance_pct", 0.0)
                        ),
                        "allocation_strategy_id": acc_strategy_map.get(acc_id),
                    }
                    type_accounts_data.append(acc_data)

                type_data = {
                    "id": type_id,
                    "code": type_code,
                    "label": type_label,
                    "actual": float(row.get(f"{type_code}_actual", 0.0)),
                    "actual_pct": float(row.get(f"{type_code}_actual_pct", 0.0)),
                    "effective": float(row.get(f"{type_code}_effective", 0.0)),
                    "effective_pct": float(row.get(f"{type_code}_effective_pct", 0.0)),
                    # Policy = same as effective for now (no separate policy targets)
                    "policy": float(row.get(f"{type_code}_effective", 0.0)),
                    "policy_pct": float(row.get(f"{type_code}_effective_pct", 0.0)),
                    "effective_variance": float(row.get(f"{type_code}_variance", 0.0)),
                    "effective_variance_pct": float(row.get(f"{type_code}_variance_pct", 0.0)),
                    # Policy variance = same as effective variance for now
                    "policy_variance": float(row.get(f"{type_code}_variance", 0.0)),
                    "policy_variance_pct": float(row.get(f"{type_code}_variance_pct", 0.0)),
                    "active_strategy_id": at_strategy_map.get(type_id),
                    "active_accounts": type_accounts_data,  # Populate active_accounts for template
                    "accounts": type_accounts_data,  # Populate accounts list for template
                }
                account_types.append(type_data)

            row_dict["account_types"] = account_types

            # Add individual account data
            accounts = []
            for _type_id, type_accounts in accounts_by_type.items():
                for account in type_accounts:
                    acc_id = account["id"]
                    type_code = account.get("type_code", "")
                    account_data = {
                        "id": acc_id,
                        "name": account["name"],
                        "type_code": type_code,
                        "actual": float(row.get(f"account_{acc_id}_actual", 0.0)),
                        "actual_pct": float(row.get(f"account_{acc_id}_actual_pct", 0.0)),
                        "target": float(row.get(f"account_{acc_id}_target", 0.0)),
                        "target_pct": float(row.get(f"account_{acc_id}_target_pct", 0.0)),
                        "variance": float(row.get(f"account_{acc_id}_variance", 0.0)),
                        "variance_pct": float(row.get(f"account_{acc_id}_variance_pct", 0.0)),
                        "allocation_strategy_id": acc_strategy_map.get(acc_id),
                    }
                    accounts.append(account_data)

            row_dict["accounts"] = accounts
            rows.append(row_dict)

        return rows

    def to_holdings_rows(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Transform holdings DataFrame to rows."""
        if df.empty:
            return []

        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "row_type": "holding",
                    "ticker": row.get("ticker", ""),
                    "name": row.get("name", ""),
                    "value": float(row.get("value", 0.0)),
                    "target_value": float(row.get("target_value", 0.0)),
                    "value_variance": float(row.get("value_variance", 0.0)),
                    "shares": float(row.get("shares", 0.0)),
                    "target_shares": float(row.get("target_shares", 0.0)),
                    "shares_variance": float(row.get("shares_variance", 0.0)),
                    "is_holding": True,
                    "is_subtotal": False,
                }
            )

        return rows

    def _format_account_types(
        self, row: pd.Series, accounts_by_type: dict[int, list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Format account type columns."""
        result = []

        for type_id, accounts in accounts_by_type.items():
            if not accounts:
                continue

            type_code = accounts[0]["type_code"]

            result.append(
                {
                    "id": type_id,
                    "code": type_code,
                    "label": accounts[0]["type_label"],
                    "actual": float(row.get(f"{type_code}_actual", 0.0)),
                    "actual_pct": float(row.get(f"{type_code}_actual_pct", 0.0)),
                    "effective": float(row.get(f"{type_code}_effective", 0.0)),
                    "effective_pct": float(row.get(f"{type_code}_effective_pct", 0.0)),
                }
            )

        return result

    # ========================================================================
    # Holdings Formatting
    # ========================================================================

    def format_holdings_rows(self, holdings_df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Format holdings DataFrame into display-ready rows with aggregations.

        Args:
            holdings_df: DataFrame with columns including:
                Ticker, Security_Name, Asset_Class, Asset_Category, Asset_Group,
                Group_Code, Category_Code, Shares, Price, Value,
                Target_Shares, Shares_Variance, Target_Value, Value_Variance,
                Allocation_Pct, Target_Allocation_Pct, Allocation_Variance_Pct

        Returns:
            List of row dicts with holdings, subtotals, group totals, and grand total
            interleaved in display order.
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
        """Convert holdings DataFrame rows to display dictionaries."""
        rows = []

        for _, row in df.iterrows():
            # Build parent_id for collapse functionality
            parent_id = f"cat-{row['Category_Code']}"

            is_zero_holding = float(row["Shares"]) == 0.0 and float(row["Value"]) == 0.0

            rows.append(
                {
                    "hierarchy_level": 999,  # Holding level
                    "ticker": row["Ticker"],
                    "security_name": row.get("Security_Name", ""),
                    "name": row.get("Security_Name", row["Ticker"]),
                    "asset_class": row["Asset_Class"],
                    "asset_category": row.get("Asset_Category", ""),
                    "asset_group": row.get("Asset_Group", ""),
                    "group_code": row.get("Group_Code", ""),
                    "category_code": row.get("Category_Code", ""),
                    "account_id": int(row.get("Account_ID", 0)),
                    "account_name": row.get("Account_Name", ""),
                    # Raw values
                    "price": float(row.get("Price", 0.0)),
                    "shares": float(row.get("Shares", 0.0)),
                    "target_shares": float(row.get("Target_Shares", 0.0)),
                    "shares_variance": float(row.get("Shares_Variance", 0.0)),
                    "value": float(row.get("Value", 0.0)),
                    "target_value": float(row.get("Target_Value", 0.0)),
                    "value_variance": float(row.get("Value_Variance", 0.0)),
                    "allocation": float(row.get("Allocation_Pct", 0.0)),
                    "target_allocation": float(row.get("Target_Allocation_Pct", 0.0)),
                    "allocation_variance": float(row.get("Allocation_Variance_Pct", 0.0)),
                    # UI metadata
                    "is_zero_holding": is_zero_holding,
                    "parent_id": parent_id,
                    "row_id": f"holding-{row['Ticker']}",
                    "holding_id": row.get("holding_id", None),
                }
            )

        return rows

    def _calculate_holdings_subtotals(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Calculate category subtotals using pandas groupby."""
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
                    "hierarchy_level": 1,  # Category subtotal
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
                    "row_id": category_id,
                    "parent_id": parent_id,
                }
            )

        return rows

    def _calculate_holdings_group_totals(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Calculate asset group totals using pandas groupby."""
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
                    "hierarchy_level": 0,  # Group total
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
                    "row_id": group_id,
                }
            )

        return rows

    def _calculate_holdings_grand_total(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Calculate grand total across all holdings."""
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
                "hierarchy_level": -1,  # Grand total
                "name": "Grand Total",
                # Raw values
                "value": float(total_value),
                "target_value": float(total_target),
                "value_variance": float(total_variance),
                "allocation": float(total_alloc),
                "target_allocation": float(total_target_alloc),
                "allocation_variance": 0.0,
            }
        ]

    def _interleave_holdings_hierarchical(
        self,
        holding_rows: list[dict[str, Any]],
        subtotal_rows: list[dict[str, Any]],
        group_rows: list[dict[str, Any]],
        grand_row: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Interleave holdings, subtotals, group totals, and grand total in display order."""
        from collections import defaultdict

        result = []

        # Build lookup maps for efficient access
        subtotals_by_category = {row["category_code"]: row for row in subtotal_rows}
        groups_by_code = {row["group_code"]: row for row in group_rows}

        # Group holdings by group_code and category_code
        holdings_by_group: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for holding in holding_rows:
            holdings_by_group[holding["group_code"]][holding["category_code"]].append(holding)

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

"""Pure calculation logic using pandas vectorization."""

from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class AllocationCalculator:
    """
    Pure pandas calculations for allocations.

    All methods are stateless and operate on DataFrames.
    """

    def calculate_allocations(self, holdings_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """
        Calculate allocations at all hierarchy levels.

        Args:
            holdings_df: MultiIndex DataFrame from Portfolio.to_dataframe()
                Rows: (Account_Type, Account_Category, Account_Name, Account_ID)
                Cols: (Asset_Class, Asset_Category, Security)
                Values: Dollar amounts

        Returns:
            Dict with allocation DataFrames:
            - 'by_account': Allocation for each account
            - 'by_account_type': Allocation for each account type
            - 'by_asset_class': Portfolio-wide by asset class
            - 'portfolio_summary': Overall portfolio summary
        """
        if holdings_df.empty:
            return self._empty_allocations()

        total_value = float(holdings_df.sum().sum())

        return {
            "by_account": self._aggregate_by_level(
                holdings_df, level="Account_ID", include_percentages=True
            ),
            "by_account_type": self._aggregate_by_level(
                holdings_df, level="Account_Type", include_percentages=True
            ),
            "by_asset_class": self._calculate_by_asset_class(holdings_df, total_value),
            "portfolio_summary": self._calculate_portfolio_summary(holdings_df, total_value),
        }

    def _aggregate_by_level(
        self,
        df: pd.DataFrame,
        level: str | list[str],
        include_percentages: bool = True,
    ) -> pd.DataFrame:
        """
        Universal aggregation method for any hierarchy level.

        Replaces _calculate_by_account, _calculate_by_account_type, etc.
        """
        # Group by asset class first
        by_asset = df.T.groupby(level="Asset_Class", observed=True).sum().T

        # Then group by specified level
        levels = [level] if isinstance(level, str) else level
        by_level = by_asset.groupby(level=levels, observed=True).sum()

        if not include_percentages:
            return by_level

        # Calculate percentages
        level_totals = by_level.sum(axis=1)
        percentages = by_level.div(level_totals, axis=0).fillna(0.0) * 100

        # Combine with _actual suffix
        result = pd.concat(
            [
                by_level.add_suffix("_actual"),
                percentages.add_suffix("_actual_pct"),
            ],
            axis=1,
        )

        return result.reindex(sorted(result.columns), axis=1)

    def _calculate_by_asset_class(self, df: pd.DataFrame, total_value: float) -> pd.DataFrame:
        """Calculate portfolio-wide allocation by asset class."""
        if total_value == 0:
            return pd.DataFrame(columns=["dollars", "percent"])

        # Sum across all accounts and securities
        by_asset = df.T.groupby(level="Asset_Class", observed=True).sum().T
        totals = by_asset.sum(axis=0)
        percentages = (totals / total_value) * 100

        result = pd.DataFrame(
            {
                "dollars": totals,
                "percent": percentages,
            }
        )

        return result.sort_values("dollars", ascending=False)

    def _calculate_portfolio_summary(self, df: pd.DataFrame, total_value: float) -> pd.DataFrame:
        """Calculate overall portfolio summary."""
        return pd.DataFrame(
            {
                "total_value": [total_value],
                "num_accounts": [len(df.index)],
                "num_holdings": [(df > 0).sum().sum()],
            }
        )

    def calculate_variances(
        self, actual_df: pd.DataFrame, targets_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate variances between actual and target allocations.

        Vectorized variance calculation using pandas merge and assign.
        """
        result = (
            actual_df.merge(
                targets_df,
                left_index=True,
                right_index=True,
                suffixes=("_actual", "_target"),
                how="outer",
            )
            .fillna(0.0)
            .assign(
                variance_value=lambda df: df.filter(like="_actual").sum(axis=1)
                - df.filter(like="_target").sum(axis=1),
                variance_pct=lambda df: (
                    df.filter(like="_actual").sum(axis=1)
                    / df.filter(like="_actual").sum(axis=1).sum()
                    * 100
                    - df.filter(like="_target").sum(axis=1)
                    / df.filter(like="_target").sum(axis=1).sum()
                    * 100
                ),
            )
        )

        return result

    def calculate_sidebar_metrics(
        self, holdings_df: pd.DataFrame, targets_map: dict[int, dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Calculate sidebar metrics using vectorized operations.

        Replaces the nested loop implementation in get_sidebar_data().

        Args:
            holdings_df: Long-format DataFrame with columns:
                account_id, asset_class, value
            targets_map: {account_id: {asset_class_name: target_pct}}

        Returns:
            Dict with:
                - account_totals: {account_id: total_value}
                - account_variances: {account_id: variance_pct}
                - grand_total: Total portfolio value
        """
        from decimal import Decimal

        if holdings_df.empty:
            return {
                "account_totals": {},
                "account_variances": {},
                "grand_total": Decimal("0.00"),
            }

        # Vectorized account totals
        account_totals = (
            holdings_df.groupby("account_id")["value"]
            .sum()
            .apply(lambda x: Decimal(str(x)))
            .to_dict()
        )

        # Vectorized variance calculation
        # Step 1: Create targets DataFrame for efficient merging
        targets_records = []
        for acc_id, allocations in targets_map.items():
            for asset_class, target_pct in allocations.items():
                targets_records.append(
                    {
                        "account_id": acc_id,
                        "asset_class": asset_class,
                        "target_pct": float(target_pct),
                    }
                )

        if targets_records:
            targets_df = pd.DataFrame(targets_records)

            # Step 2: Merge holdings with targets (true vectorization)
            holdings_with_targets = holdings_df.merge(
                targets_df, on=["account_id", "asset_class"], how="left"
            ).fillna({"target_pct": 0.0})
        else:
            holdings_with_targets = holdings_df.copy()
            holdings_with_targets["target_pct"] = 0.0

        # Step 3: Calculate target values and deviations
        account_totals_series = holdings_df.groupby("account_id")["value"].sum()
        holdings_with_targets["account_total"] = holdings_with_targets["account_id"].map(
            account_totals_series
        )
        holdings_with_targets["target_value"] = holdings_with_targets["account_total"] * (
            holdings_with_targets["target_pct"] / 100.0
        )
        holdings_with_targets["deviation"] = abs(
            holdings_with_targets["value"] - holdings_with_targets["target_value"]
        )

        # Step 4: Aggregate variances by account
        variances = (
            holdings_with_targets.groupby("account_id")
            .apply(
                lambda g: (
                    (g["deviation"].sum() / g["account_total"].iloc[0] * 100)
                    if g["account_total"].iloc[0] > 0
                    else 0.0
                ),
                include_groups=False,
            )
            .to_dict()
        )

        grand_total = sum(account_totals.values(), Decimal("0.00"))

        return {
            "account_totals": account_totals,
            "account_variances": variances,
            "grand_total": grand_total,
        }

    def _empty_allocations(self) -> dict[str, pd.DataFrame]:
        """Return empty DataFrames for empty portfolio."""
        return {
            "by_account": pd.DataFrame(),
            "by_account_type": pd.DataFrame(),
            "by_asset_class": pd.DataFrame(),
            "portfolio_summary": pd.DataFrame(),
        }

    # ========================================================================
    # Helper Methods for Unified Aggregation
    # ========================================================================

    def _pivot_and_merge(
        self,
        df: pd.DataFrame,
        data_df: pd.DataFrame,
        level_column: str,
        column_prefix: str = "",
        suffix: str = "_actual",
    ) -> pd.DataFrame:
        """
        Universal pivot-flatten-merge pattern.

        Handles: reset → pivot → flatten → merge
        """
        data_reset = data_df.reset_index()

        pivoted = data_reset.pivot(
            index="asset_class_id",
            columns=level_column,
            values=["value", "pct"],
        )

        # Flatten column names
        pivoted.columns = [
            f"{column_prefix}{col[1]}{suffix}"
            if col[0] == "value"
            else f"{column_prefix}{col[1]}{suffix}_pct"
            for col in pivoted.columns
        ]

        result = df.merge(pivoted, left_on="asset_class_id", right_index=True, how="left")
        return result.fillna(0.0)

    def _aggregate_actuals_by_level(
        self,
        df: pd.DataFrame,
        holdings_df: pd.DataFrame,
        level: str,
        level_column: str | None = None,
    ) -> pd.DataFrame:
        """
        Unified aggregation for actual allocations at any hierarchy level.

        Replaces:
        - _add_portfolio_calculations_presentation
        - _add_account_type_calculations_presentation
        - _add_account_calculations_presentation

        Args:
            df: Base DataFrame with asset_class metadata
            holdings_df: Long-format holdings
            level: 'portfolio', 'account_type', or 'account'
            level_column: Column to group by (None for portfolio)

        Returns:
            DataFrame with added actual/actual_pct columns
        """
        if holdings_df.empty:
            return df

        # Determine grouping
        if level == "portfolio":
            group_cols: list[str] = ["asset_class_id"]
        else:
            assert level_column is not None, "level_column required for non-portfolio levels"
            group_cols = [level_column, "asset_class_id"]

        # Aggregate values
        aggregated = holdings_df.groupby(group_cols)["value"].sum().to_frame(name="value")

        # Calculate percentages
        if level == "portfolio":
            total = aggregated["value"].sum()
            aggregated["pct"] = aggregated["value"] / total * 100 if total > 0 else 0.0
        else:
            aggregated["pct"] = aggregated.groupby(level=0)["value"].transform(
                lambda x: x / x.sum() * 100 if x.sum() > 0 else 0.0
            )

        # Merge back
        if level == "portfolio":
            aggregated.columns = ["portfolio_actual", "portfolio_actual_pct"]
            result = df.merge(aggregated, left_on="asset_class_id", right_index=True, how="left")
        else:
            column_prefix = "account_" if level == "account" else ""
            # level_column is guaranteed not None by assertion above
            assert level_column is not None
            result = self._pivot_and_merge(
                df, aggregated, level_column, column_prefix=column_prefix, suffix="_actual"
            )

        return result.fillna(0.0)

    def _calculate_variance_for_columns(
        self,
        df: pd.DataFrame,
        actual_col: str,
        target_col: str,
        variance_col: str,
    ) -> pd.DataFrame:
        """Calculate variance = actual - target for any column pair."""
        # Value variance
        if actual_col in df.columns and target_col in df.columns:
            df[variance_col] = df[actual_col] - df[target_col]

        # Percentage variance
        actual_pct = f"{actual_col}_pct"
        target_pct = f"{target_col}_pct"
        variance_pct = f"{variance_col}_pct"

        if actual_pct in df.columns and target_pct in df.columns:
            df[variance_pct] = df[actual_pct] - df[target_pct]

        return df

    # ========================================================================
    # Presentation Calculation Pipeline
    # ========================================================================

    def build_presentation_dataframe(
        self,
        holdings_df: pd.DataFrame,
        asset_classes_df: pd.DataFrame,
        targets_map: dict[int, dict[str, Any]],
        account_totals: dict[int, Any],
        policy_targets: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        """
        Build complete presentation DataFrame with all calculations.

        This orchestrates the full calculation pipeline:
        1. Start with base asset class metadata
        2. Add portfolio-level actuals
        3. Add account-type level actuals
        4. Add individual account actuals
        5. Calculate weighted effective targets
        6. Calculate policy targets (portfolio-level stated targets)
        7. Calculate variances at all levels
        8. Sort by hierarchy

        Args:
            holdings_df: Long-format holdings
            asset_classes_df: Asset class metadata
            targets_map: {account_id: {asset_class_name: target_pct}}
            account_totals: {account_id: total_value}
            policy_targets: {asset_class_name: target_pct} from portfolio strategy

        Returns:
            DataFrame with columns for each level:
            - asset_class metadata (name, id, group, category)
            - portfolio_actual, portfolio_actual_pct
            - {type}_actual, {type}_actual_pct for each account type
            - {account}_actual, {account}_actual_pct for each account
            - portfolio_effective, portfolio_effective_pct
            - {type}_effective, {type}_effective_pct
            - portfolio_policy, portfolio_policy_pct (stated targets)
            - portfolio_variance, portfolio_variance_pct (vs effective)
            - portfolio_policy_variance, portfolio_policy_variance_pct (vs policy)
            - {type}_variance, {type}_variance_pct
        """
        if holdings_df.empty:
            return pd.DataFrame()

        # Step 1: Base DataFrame with all asset classes
        df = asset_classes_df.copy()

        # Step 2-4: Add actuals at all levels using unified method
        df = self._aggregate_actuals_by_level(df, holdings_df, level="portfolio")
        df = self._aggregate_actuals_by_level(
            df, holdings_df, level="account_type", level_column="account_type_code"
        )
        df = self._aggregate_actuals_by_level(
            df, holdings_df, level="account", level_column="account_id"
        )

        # Step 5: Calculate weighted effective targets
        # Build account_type_map from holdings_df: {account_id: account_type_code}
        account_type_map = (
            holdings_df[["account_id", "account_type_code"]]
            .drop_duplicates()
            .set_index("account_id")["account_type_code"]
            .to_dict()
        )
        df = self._calculate_weighted_targets_presentation(
            df, targets_map, account_totals, account_type_map
        )

        # Step 6: Calculate policy targets (portfolio-level stated targets)
        from decimal import Decimal

        portfolio_total = float(sum(account_totals.values(), Decimal("0")))
        df = self._calculate_policy_targets_presentation(df, policy_targets, portfolio_total)

        # Step 7: Calculate variances (both effective and policy)
        df = self._calculate_variances_presentation(df)

        # Step 8: Sort by hierarchy
        df = self._sort_presentation_dataframe(df)

        # Step 9: Add subtotal and grand total rows
        df = self._add_aggregated_rows(df)

        return df

    def _add_aggregated_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add category subtotals, group subtotals, and grand total rows.

        Uses pandas groupby aggregation for vectorized performance.
        """
        if df.empty:
            return df

        # Identify numeric columns to aggregate (all actual, effective, policy, variance columns)
        numeric_cols = [
            col
            for col in df.columns
            if any(
                suffix in col
                for suffix in [
                    "_actual",
                    "_actual_pct",
                    "_effective",
                    "_effective_pct",
                    "_policy",
                    "_policy_pct",
                    "_variance",
                    "_variance_pct",
                ]
            )
        ]

        result_rows = []

        # Get unique groups and categories for aggregation
        groups = df["group_code"].unique()

        for group in groups:
            group_df = df[df["group_code"] == group]
            categories = group_df["category_code"].unique()

            for category in categories:
                category_df = group_df[group_df["category_code"] == category]

                # Add individual asset class rows
                for _, row in category_df.iterrows():
                    row_dict = row.to_dict()
                    row_dict["hierarchy_level"] = 999  # Asset class level
                    result_rows.append(row_dict)

                # Add category subtotal if more than 1 asset class in category
                if len(category_df) > 1:
                    category_total = category_df[numeric_cols].sum()
                    category_row = {
                        "asset_class_name": f"{category_df.iloc[0]['category_label']} Total",
                        "asset_class_id": 0,
                        "group_code": group,
                        "group_label": category_df.iloc[0]["group_label"],
                        "category_code": category,
                        "category_label": category_df.iloc[0]["category_label"],
                        "is_cash": False,
                        "hierarchy_level": 1,  # Category subtotal
                        "group_sort_order": category_df.iloc[0].get("group_sort_order", 0),
                        "category_sort_order": category_df.iloc[0].get("category_sort_order", 0),
                    }
                    # Add aggregated numeric values
                    for col in numeric_cols:
                        category_row[col] = category_total[col]
                    result_rows.append(category_row)

            # Add group subtotal if more than 1 category in group
            if len(categories) > 1:
                group_total = group_df[numeric_cols].sum()
                group_row = {
                    "asset_class_name": f"{group_df.iloc[0]['group_label']} Total",
                    "asset_class_id": 0,
                    "group_code": group,
                    "group_label": group_df.iloc[0]["group_label"],
                    "category_code": "",
                    "category_label": "",
                    "is_cash": False,
                    "hierarchy_level": 0,  # Group total
                    "group_sort_order": group_df.iloc[0].get("group_sort_order", 0),
                    "category_sort_order": 999,  # Sort at end of group
                }
                # Add aggregated numeric values
                for col in numeric_cols:
                    group_row[col] = group_total[col]
                result_rows.append(group_row)

        # Add grand total row
        grand_total = df[numeric_cols].sum()
        grand_row = {
            "asset_class_name": "Total",
            "asset_class_id": 0,
            "group_code": "",
            "group_label": "",
            "category_code": "",
            "category_label": "",
            "is_cash": False,
            "hierarchy_level": -1,  # Grand total
            "group_sort_order": 999,
            "category_sort_order": 999,
        }
        # Add aggregated numeric values
        for col in numeric_cols:
            grand_row[col] = grand_total[col]
        result_rows.append(grand_row)

        return pd.DataFrame(result_rows)

    def _calculate_weighted_targets_presentation(
        self,
        df: pd.DataFrame,
        targets_map: dict[int, dict[str, Any]],
        account_totals: dict[int, Any],
        account_type_map: dict[int, str] | None = None,
    ) -> pd.DataFrame:
        """
        Calculate effective (weighted) targets at all levels.

        Effective target = weighted average of account targets,
        weighted by account values.

        Args:
            df: DataFrame with asset class data and actuals
            targets_map: {account_id: {asset_class_name: target_pct}}
            account_totals: {account_id: total_value}
            account_type_map: {account_id: account_type_code}
        """
        from decimal import Decimal

        if not targets_map:
            # No targets - add zero columns
            df["portfolio_effective"] = 0.0
            df["portfolio_effective_pct"] = 0.0
            return df

        account_type_map = account_type_map or {}

        # Build targets DataFrame with account metadata
        targets_records = []
        for acc_id, allocations in targets_map.items():
            acc_total = float(account_totals.get(acc_id, Decimal("0")))
            acc_type = account_type_map.get(acc_id, "")

            for asset_class_name, target_pct in allocations.items():
                targets_records.append(
                    {
                        "account_id": acc_id,
                        "account_type_code": acc_type,
                        "asset_class": asset_class_name,
                        "target_pct": float(target_pct),
                        "account_total": acc_total,
                    }
                )

        if not targets_records:
            df["portfolio_effective"] = 0.0
            df["portfolio_effective_pct"] = 0.0
            return df

        targets_df = pd.DataFrame(targets_records)

        # Merge with asset class metadata to get asset_class_id
        targets_with_id = targets_df.merge(
            df[["asset_class_name", "asset_class_id"]].drop_duplicates(),
            left_on="asset_class",
            right_on="asset_class_name",
            how="left",
        )

        # Portfolio-level weighted targets
        portfolio_total = float(sum(account_totals.values(), Decimal("0")))

        if portfolio_total > 0:
            portfolio_weighted = (
                targets_with_id.groupby("asset_class_id")
                .apply(
                    lambda x: (x["target_pct"] * x["account_total"]).sum() / portfolio_total,
                    include_groups=False,
                )
                .to_frame(name="portfolio_effective_pct")
            )

            portfolio_weighted["portfolio_effective"] = (
                portfolio_weighted["portfolio_effective_pct"] * portfolio_total / 100
            )
        else:
            portfolio_weighted = pd.DataFrame(
                {
                    "portfolio_effective": 0.0,
                    "portfolio_effective_pct": 0.0,
                }
            )

        # Merge with main DataFrame
        result = df.merge(
            portfolio_weighted,
            left_on="asset_class_id",
            right_index=True,
            how="left",
        ).fillna(0.0)

        # Account-type level effective targets
        # Calculate weighted effective targets for each account type
        # Get unique account types from column names
        type_columns = [
            col.replace("_actual", "")
            for col in result.columns
            if col.endswith("_actual")
            and not col.startswith("account_")
            and col != "portfolio_actual"
        ]

        # Calculate type totals for weighting
        type_totals: dict[str, float] = {}
        for acc_id, acc_type in account_type_map.items():
            if acc_type:
                acc_total = float(account_totals.get(acc_id, Decimal("0")))
                type_totals[acc_type] = type_totals.get(acc_type, 0.0) + acc_total

        # For each account type, calculate weighted effective targets
        for type_code in type_columns:
            type_total = type_totals.get(type_code, 0.0)

            if type_total > 0 and not targets_with_id.empty:
                # Filter targets to accounts of this type
                type_targets = targets_with_id[targets_with_id["account_type_code"] == type_code]

                if not type_targets.empty:
                    # Calculate weighted effective for this type
                    # Bind type_total to lambda's local scope to avoid B023
                    type_weighted = (
                        type_targets.groupby("asset_class_id")
                        .apply(
                            lambda x, tt=type_total: (x["target_pct"] * x["account_total"]).sum()
                            / tt,
                            include_groups=False,
                        )
                        .to_frame(name=f"{type_code}_effective_pct")
                    )

                    type_weighted[f"{type_code}_effective"] = (
                        type_weighted[f"{type_code}_effective_pct"] * type_total / 100
                    )

                    # Merge with result
                    result = result.merge(
                        type_weighted,
                        left_on="asset_class_id",
                        right_index=True,
                        how="left",
                        suffixes=("", "_new"),
                    )

                    # Handle column collision if effective columns already exist
                    if f"{type_code}_effective_new" in result.columns:
                        result[f"{type_code}_effective"] = result[
                            f"{type_code}_effective_new"
                        ].fillna(0.0)
                        result[f"{type_code}_effective_pct"] = result[
                            f"{type_code}_effective_pct_new"
                        ].fillna(0.0)
                        result = result.drop(
                            columns=[
                                f"{type_code}_effective_new",
                                f"{type_code}_effective_pct_new",
                            ]
                        )
                    else:
                        result[f"{type_code}_effective"] = result[f"{type_code}_effective"].fillna(
                            0.0
                        )
                        result[f"{type_code}_effective_pct"] = result[
                            f"{type_code}_effective_pct"
                        ].fillna(0.0)
                else:
                    # No targets for this type - set to 0
                    result[f"{type_code}_effective"] = 0.0
                    result[f"{type_code}_effective_pct"] = 0.0
            else:
                # No accounts of this type or no total - set to 0
                result[f"{type_code}_effective"] = 0.0
                result[f"{type_code}_effective_pct"] = 0.0

        return result

    def _calculate_policy_targets_presentation(
        self,
        df: pd.DataFrame,
        policy_targets: dict[str, Any] | None,
        portfolio_total: float,
    ) -> pd.DataFrame:
        """
        Calculate policy targets at portfolio level.

        Policy targets come from the portfolio's allocation_strategy and represent
        the user's stated target allocation, as opposed to effective targets which
        are weighted averages of account-level targets.

        Args:
            df: DataFrame with asset class data
            policy_targets: {asset_class_name: target_pct} from portfolio strategy
            portfolio_total: Total portfolio value for dollar calculations
        """
        if not policy_targets:
            # No policy targets - set to 0
            df["portfolio_policy"] = 0.0
            df["portfolio_policy_pct"] = 0.0
            return df

        # Map policy targets by asset class name
        df["portfolio_policy_pct"] = df["asset_class_name"].map(
            lambda name: float(policy_targets.get(name, 0))
        )

        # Calculate dollar value based on percentage and total
        df["portfolio_policy"] = df["portfolio_policy_pct"] * portfolio_total / 100

        return df

    def _calculate_variances_presentation(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate variances between actual and effective/policy allocations.

        For each level (portfolio, account types, accounts):
        - effective_variance = actual - effective (for rebalancing)
        - policy_variance = actual - policy (for policy adherence)
        """
        # Portfolio variances
        df = self._calculate_variance_for_columns(
            df, "portfolio_actual", "portfolio_effective", "portfolio_variance"
        )
        df = self._calculate_variance_for_columns(
            df, "portfolio_actual", "portfolio_policy", "portfolio_policy_variance"
        )

        # Account type variances (dynamic)
        type_columns = [
            col.replace("_actual", "")
            for col in df.columns
            if col.endswith("_actual")
            and not col.startswith("account_")
            and col != "portfolio_actual"
        ]
        for type_prefix in type_columns:
            df = self._calculate_variance_for_columns(
                df, f"{type_prefix}_actual", f"{type_prefix}_effective", f"{type_prefix}_variance"
            )

        # Account variances (dynamic)
        account_columns = [
            col.replace("_actual", "")
            for col in df.columns
            if col.startswith("account_") and col.endswith("_actual")
        ]
        for account_prefix in account_columns:
            df = self._calculate_variance_for_columns(
                df,
                f"{account_prefix}_actual",
                f"{account_prefix}_target",
                f"{account_prefix}_variance",
            )

        return df

    def _sort_presentation_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Sort DataFrame by hierarchy and policy allocation.

        Sorting priority:
        1. group_sort_order (ascending) - if exists
        2. group_code (ascending)
        3. category_sort_order (ascending) - if exists
        4. category_code (ascending)
        5. portfolio_effective (descending) - policy allocation
        6. asset_class_name (ascending) - tie breaker
        """
        sort_columns = []
        ascending_flags = []

        # Group level
        if "group_sort_order" in df.columns:
            sort_columns.append("group_sort_order")
            ascending_flags.append(True)

        if "group_code" in df.columns:
            sort_columns.append("group_code")
            ascending_flags.append(True)

        # Category level
        if "category_sort_order" in df.columns:
            sort_columns.append("category_sort_order")
            ascending_flags.append(True)

        if "category_code" in df.columns:
            sort_columns.append("category_code")
            ascending_flags.append(True)

        # Asset level - sort by policy allocation descending
        if "portfolio_effective" in df.columns:
            sort_columns.append("portfolio_effective")
            ascending_flags.append(False)  # Descending

        if "asset_class_name" in df.columns:
            sort_columns.append("asset_class_name")
            ascending_flags.append(True)

        if sort_columns:
            return df.sort_values(by=sort_columns, ascending=ascending_flags)

        return df

    # ========================================================================
    # Holdings Calculation Pipeline
    # ========================================================================

    def calculate_holdings_with_targets(
        self,
        holdings_df: pd.DataFrame,
        targets_map: dict[int, dict[str, Any]],
    ) -> pd.DataFrame:
        """
        Calculate holdings with target allocations and variances.

        Args:
            holdings_df: DataFrame with columns:
                Account_ID, Account_Name, Account_Type, Ticker, Security_Name,
                Asset_Class, Asset_Class_ID, Asset_Category, Asset_Group,
                Group_Code, Group_Sort_Order, Category_Code, Category_Sort_Order,
                Shares, Price, Value
            targets_map: {account_id: {asset_class_name: target_pct}}

        Returns:
            DataFrame with additional columns:
                Target_Value, Value_Variance, Target_Shares, Shares_Variance,
                Allocation_Pct, Target_Allocation_Pct, Allocation_Variance_Pct
        """
        if holdings_df.empty:
            return pd.DataFrame()

        df = holdings_df.copy()

        # Calculate total value (for allocation percentages)
        total_value = df["Value"].sum()

        # Build targets DataFrame for efficient merging
        targets_records = []
        for acc_id, allocations in targets_map.items():
            for asset_class_name, target_pct in allocations.items():
                targets_records.append(
                    {
                        "Account_ID": acc_id,
                        "Asset_Class": asset_class_name,
                        "Target_Pct": float(target_pct),
                    }
                )

        if targets_records:
            targets_df = pd.DataFrame(targets_records)
            df = df.merge(targets_df, on=["Account_ID", "Asset_Class"], how="left")
        else:
            df["Target_Pct"] = 0.0

        df["Target_Pct"] = df["Target_Pct"].fillna(0.0)

        # Calculate account totals for target value calculation
        account_totals = df.groupby("Account_ID")["Value"].sum()
        df["Account_Total"] = df["Account_ID"].map(account_totals)

        # Count securities per asset class per account (for splitting target across holdings)
        sec_counts = df.groupby(["Account_ID", "Asset_Class"])["Ticker"].transform("count")
        df["Sec_Count"] = sec_counts

        # Calculate target value (split across securities in same asset class)
        df["Target_Value"] = 0.0
        mask = df["Sec_Count"] > 0
        if mask.any():
            df.loc[mask, "Target_Value"] = (
                df.loc[mask, "Account_Total"]
                * (df.loc[mask, "Target_Pct"] / 100.0)
                / df.loc[mask, "Sec_Count"]
            )

        # Calculate value variance
        df["Value_Variance"] = df["Value"] - df["Target_Value"]

        # Calculate allocation percentages
        if total_value > 0:
            df["Allocation_Pct"] = (df["Value"] / total_value) * 100
            df["Target_Allocation_Pct"] = (df["Target_Value"] / total_value) * 100
        else:
            df["Allocation_Pct"] = 0.0
            df["Target_Allocation_Pct"] = 0.0

        df["Allocation_Variance_Pct"] = df["Allocation_Pct"] - df["Target_Allocation_Pct"]

        # Calculate share targets and variances
        df["Target_Shares"] = 0.0
        price_mask = df["Price"] > 0
        if price_mask.any():
            df.loc[price_mask, "Target_Shares"] = (
                df.loc[price_mask, "Target_Value"] / df.loc[price_mask, "Price"]
            )
        df["Shares_Variance"] = df["Shares"] - df["Target_Shares"]

        # Sort by hierarchy
        df = df.sort_values(
            by=["Group_Sort_Order", "Category_Sort_Order", "Target_Value", "Ticker"],
            ascending=[True, True, False, True],
        )

        # Clean up temporary columns
        df = df.drop(columns=["Account_Total", "Sec_Count"], errors="ignore")

        return df

    def aggregate_holdings_by_ticker(self, holdings_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate holdings across all accounts by ticker.

        Args:
            holdings_df: DataFrame with holdings from multiple accounts

        Returns:
            DataFrame aggregated by Ticker with summed Shares and Value
        """
        if holdings_df.empty:
            return pd.DataFrame()

        agg_dict = {
            "Shares": "sum",
            "Value": "sum",
            "Security_Name": "first",
            "Asset_Class": "first",
            "Asset_Class_ID": "first",
            "Asset_Category": "first",
            "Asset_Group": "first",
            "Group_Code": "first",
            "Group_Sort_Order": "first",
            "Category_Code": "first",
            "Category_Sort_Order": "first",
            "Price": "first",
        }

        # Only include columns that exist
        agg_dict = {k: v for k, v in agg_dict.items() if k in holdings_df.columns}

        df_aggregated = holdings_df.groupby("Ticker", as_index=False).agg(agg_dict)

        # Set synthetic portfolio account ID
        df_aggregated["Account_ID"] = 0
        df_aggregated["Account_Name"] = "Portfolio"
        df_aggregated["Account_Type"] = ""

        return df_aggregated


class AllocationAggregator:
    """
    Helper class to calculate aggregated subtotals and totals from a DataFrame.
    
    Used primarily by the rebalancing engine to compute current and pro forma
    aggregated stats efficiently.
    """

    def __init__(self, df: pd.DataFrame):
        """
        Initialize with a DataFrame containing asset/holding data.
        
        Args:
            df: DataFrame containing at least:
                - value (Decimal or float)
                - asset_class (AssetClass object)
                - asset_class_id (int)
        """
        self.df = df
        self.aggregated_context: dict[str, Any] = {}

    def calculate_aggregations(self) -> None:
        """Calculate totals by asset class and portfolio."""
        from decimal import Decimal
        
        if self.df.empty:
            self.aggregated_context = {
                "asset_class": {},
                "grand_total": {"total_value": Decimal("0"), "allocation_percent": Decimal("0")},
            }
            return

        # Ensure value is float for calculation
        # The input df usually has 'value' as Decimal from database
        self.df = self.df.copy()
        
        # Handle potential empty or mixed types in value
        if "value" in self.df.columns:
            self.df["value_float"] = self.df["value"].apply(lambda x: float(x) if x is not None else 0.0)
        else:
            self.df["value_float"] = 0.0
            
        total_value = self.df["value_float"].sum()

        # 1. Asset Class Aggregation
        # Group by asset_class_id
        if "asset_class_id" in self.df.columns:
            ac_grouped = self.df.groupby("asset_class_id")
            ac_data = {}
            for ac_id, group in ac_grouped:
                ac_total = group["value_float"].sum()
                ac_pct = (ac_total / total_value * 100) if total_value > 0 else 0
                ac_data[ac_id] = {
                    "total_value": Decimal(str(ac_total)),
                    "allocation_percent": Decimal(str(ac_pct)),
                }
        else:
            ac_data = {}

        # 2. Grand Total
        grand_total_data = {
            "total_value": Decimal(str(total_value)),
            "allocation_percent": Decimal("100.0"),
        }

        self.aggregated_context = {
            "asset_class": ac_data,
            "grand_total": grand_total_data,
        }

    def build_context(self) -> dict[str, Any]:
        """Return the aggregated context."""
        return self.aggregated_context

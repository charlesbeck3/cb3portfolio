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
    # Presentation Calculation Pipeline
    # ========================================================================

    def build_presentation_dataframe(
        self,
        holdings_df: pd.DataFrame,
        asset_classes_df: pd.DataFrame,
        targets_map: dict[int, dict[str, Any]],
        account_totals: dict[int, Any],
    ) -> pd.DataFrame:
        """
        Build complete presentation DataFrame with all calculations.

        This orchestrates the full calculation pipeline:
        1. Start with base asset class metadata
        2. Add portfolio-level actuals
        3. Add account-type level actuals
        4. Add individual account actuals
        5. Calculate weighted effective targets
        6. Calculate variances at all levels
        7. Sort by hierarchy

        Args:
            holdings_df: Long-format holdings
            asset_classes_df: Asset class metadata
            targets_map: {account_id: {asset_class_name: target_pct}}
            account_totals: {account_id: total_value}

        Returns:
            DataFrame with columns for each level:
            - asset_class metadata (name, id, group, category)
            - portfolio_actual, portfolio_actual_pct
            - {type}_actual, {type}_actual_pct for each account type
            - {account}_actual, {account}_actual_pct for each account
            - portfolio_effective, portfolio_effective_pct
            - {type}_effective, {type}_effective_pct
            - portfolio_variance, portfolio_variance_pct
            - {type}_variance, {type}_variance_pct
        """
        if holdings_df.empty:
            return pd.DataFrame()

        # Step 1: Base DataFrame with all asset classes
        df = asset_classes_df.copy()

        # Step 2: Add portfolio-level calculations
        df = self._add_portfolio_calculations_presentation(df, holdings_df)

        # Step 3: Add account-type level calculations
        df = self._add_account_type_calculations_presentation(df, holdings_df)

        # Step 4: Add individual account calculations
        df = self._add_account_calculations_presentation(df, holdings_df)

        # Step 5: Calculate weighted effective targets
        df = self._calculate_weighted_targets_presentation(df, targets_map, account_totals)

        # Step 6: Calculate variances
        df = self._calculate_variances_presentation(df)

        # Step 7: Sort by hierarchy
        df = self._sort_presentation_dataframe(df)

        # Step 8: Add subtotal and grand total rows
        df = self._add_aggregated_rows(df)

        return df

    def _add_aggregated_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add category subtotals, group subtotals, and grand total rows.

        Uses pandas groupby aggregation for vectorized performance.
        """
        if df.empty:
            return df

        # Identify numeric columns to aggregate (all actual, effective, variance columns)
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
                    result_rows.append(row.to_dict())

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
                        "row_type": "subtotal",  # Changed from category_total
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
                    "row_type": "group_total",
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
            "row_type": "grand_total",
            "group_sort_order": 999,
            "category_sort_order": 999,
        }
        # Add aggregated numeric values
        for col in numeric_cols:
            grand_row[col] = grand_total[col]
        result_rows.append(grand_row)

        return pd.DataFrame(result_rows)

    def _add_portfolio_calculations_presentation(
        self,
        df: pd.DataFrame,
        holdings_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Add portfolio-level actual allocations."""
        portfolio_total = holdings_df["value"].sum()

        # Aggregate by asset class
        by_asset = (
            holdings_df.groupby("asset_class_id")["value"].sum().to_frame(name="portfolio_actual")
        )

        # Calculate percentages
        if portfolio_total > 0:
            by_asset["portfolio_actual_pct"] = by_asset["portfolio_actual"] / portfolio_total * 100
        else:
            by_asset["portfolio_actual_pct"] = 0.0

        # Merge with main DataFrame
        result = df.merge(
            by_asset,
            left_on="asset_class_id",
            right_index=True,
            how="left",
        ).fillna(0.0)

        return result

    def _add_account_type_calculations_presentation(
        self,
        df: pd.DataFrame,
        holdings_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Add account-type level actual allocations."""
        # Group by account type and asset class
        by_type = (
            holdings_df.groupby(["account_type_code", "asset_class_id"])["value"]
            .sum()
            .to_frame(name="value")
        )

        # Add percentage column using groupby transform
        by_type["pct"] = by_type.groupby(level="account_type_code")["value"].transform(
            lambda x: x / x.sum() * 100 if x.sum() > 0 else 0.0
        )

        # Pivot to get columns per account type
        by_type_reset = by_type.reset_index()
        by_type_pivot = by_type_reset.pivot(
            index="asset_class_id",
            columns="account_type_code",
            values=["value", "pct"],
        )

        # Flatten column names: (value, 401k) -> 401k_actual
        by_type_pivot.columns = [
            f"{col[1]}_actual" if col[0] == "value" else f"{col[1]}_actual_pct"
            for col in by_type_pivot.columns
        ]

        # Merge with main DataFrame
        result = df.merge(
            by_type_pivot,
            left_on="asset_class_id",
            right_index=True,
            how="left",
        ).fillna(0.0)

        return result

    def _add_account_calculations_presentation(
        self,
        df: pd.DataFrame,
        holdings_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Add individual account level actual allocations."""
        # Group by account and asset class
        by_account = (
            holdings_df.groupby(["account_id", "asset_class_id"])["value"]
            .sum()
            .to_frame(name="value")
        )

        # Calculate percentages within each account
        by_account["pct"] = by_account.groupby(level="account_id")["value"].transform(
            lambda x: x / x.sum() * 100 if x.sum() > 0 else 0.0
        )

        # Pivot to get columns per account
        by_account_reset = by_account.reset_index()
        by_account_pivot = by_account_reset.pivot(
            index="asset_class_id",
            columns="account_id",
            values=["value", "pct"],
        )

        # Flatten column names: (value, 123) -> account_123_actual
        by_account_pivot.columns = [
            f"account_{col[1]}_actual" if col[0] == "value" else f"account_{col[1]}_actual_pct"
            for col in by_account_pivot.columns
        ]

        # Merge with main DataFrame
        result = df.merge(
            by_account_pivot,
            left_on="asset_class_id",
            right_index=True,
            how="left",
        ).fillna(0.0)

        return result

    def _calculate_weighted_targets_presentation(
        self,
        df: pd.DataFrame,
        targets_map: dict[int, dict[str, Any]],
        account_totals: dict[int, Any],
    ) -> pd.DataFrame:
        """
        Calculate effective (weighted) targets at all levels.

        Effective target = weighted average of account targets,
        weighted by account values.
        """
        from decimal import Decimal

        if not targets_map:
            # No targets - add zero columns
            df["portfolio_effective"] = 0.0
            df["portfolio_effective_pct"] = 0.0
            return df

        # Build targets DataFrame with account metadata
        targets_records = []
        for acc_id, allocations in targets_map.items():
            acc_total = float(account_totals.get(acc_id, Decimal("0")))

            for asset_class_name, target_pct in allocations.items():
                targets_records.append(
                    {
                        "account_id": acc_id,
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
        # Need to get account type for each account from holdings_df
        # For now, we'll use the fact that account type columns exist in the DataFrame
        # Get unique account types from column names
        type_columns = [
            col.replace("_actual", "")
            for col in result.columns
            if col.endswith("_actual")
            and not col.startswith("account_")
            and col != "portfolio_actual"
        ]

        # For each account type, calculate weighted effective targets
        # This is a workaround - ideally we'd pass account type mapping
        # For now, calculate effective = actual (no weighting at type level)
        # TODO: Implement proper account-type level weighted targets
        for type_code in type_columns:
            result[f"{type_code}_effective"] = result[f"{type_code}_actual"]
            result[f"{type_code}_effective_pct"] = result[f"{type_code}_actual_pct"]

        return result

    def _calculate_variances_presentation(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate variances between actual and effective/target allocations.

        For each level (portfolio, account types, accounts):
        - variance = actual - effective
        - variance_pct = actual_pct - effective_pct
        """
        # Portfolio level
        if "portfolio_actual" in df.columns and "portfolio_effective" in df.columns:
            df["portfolio_variance"] = df["portfolio_actual"] - df["portfolio_effective"]
            df["portfolio_variance_pct"] = (
                df["portfolio_actual_pct"] - df["portfolio_effective_pct"]
            )

        # Account type level - find all type columns dynamically
        type_columns = [
            col
            for col in df.columns
            if col.endswith("_actual")
            and not col.startswith("account_")
            and col != "portfolio_actual"
        ]

        for actual_col in type_columns:
            type_prefix = actual_col.replace("_actual", "")
            effective_col = f"{type_prefix}_effective"

            if effective_col in df.columns:
                df[f"{type_prefix}_variance"] = df[actual_col] - df[effective_col]

                # Percentage variance
                actual_pct_col = f"{type_prefix}_actual_pct"
                effective_pct_col = f"{type_prefix}_effective_pct"
                if actual_pct_col in df.columns and effective_pct_col in df.columns:
                    df[f"{type_prefix}_variance_pct"] = df[actual_pct_col] - df[effective_pct_col]

        # Individual account level
        account_columns = [
            col for col in df.columns if col.startswith("account_") and col.endswith("_actual")
        ]

        for actual_col in account_columns:
            account_prefix = actual_col.replace("_actual", "")
            target_col = f"{account_prefix}_target"

            if target_col in df.columns:
                df[f"{account_prefix}_variance"] = df[actual_col] - df[target_col]

                actual_pct_col = f"{account_prefix}_actual_pct"
                target_pct_col = f"{account_prefix}_target_pct"
                if actual_pct_col in df.columns and target_pct_col in df.columns:
                    df[f"{account_prefix}_variance_pct"] = df[actual_pct_col] - df[target_pct_col]

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

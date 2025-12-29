"""
Pure pandas-based allocation calculations using MultiIndex DataFrames.
Zero Django dependencies - can be tested with mock DataFrames.

DESIGN PHILOSOPHY:
- Store ONLY numeric values in DataFrames (no formatting)
- Use MultiIndex for natural hierarchy representation
- Single aggregation pattern using pandas groupby
- Formatting happens in views/templates, not here
"""

from decimal import Decimal
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class AllocationCalculationEngine:
    """
    Calculate portfolio allocations at all hierarchy levels using pandas.

    All methods return DataFrames with raw numeric values.
    Views/templates are responsible for formatting display strings.
    """

    def __init__(self) -> None:
        logger.debug("initializing_allocation_engine")

    def calculate_allocations(
        self,
        holdings_df: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        """
        Calculate allocations at all levels from portfolio holdings.

        Args:
            holdings_df: MultiIndex DataFrame from Portfolio.to_dataframe()
                Rows: (Account_Type, Account_Category, Account_Name, Account_ID)
                Cols: (Asset_Class, Asset_Category, Security)
                Values: Dollar amounts

        Returns:
            Dict with allocation DataFrames (all with numeric values only):
            - 'by_account': Allocation for each account
            - 'by_account_type': Allocation for each account type
            - 'by_asset_class': Portfolio-wide by asset class
            - 'portfolio_summary': Overall portfolio summary
        """
        if holdings_df.empty:
            logger.debug("calculate_allocations_empty")
            return self._empty_allocations()

        logger.info(
            "calculating_allocations",
            holdings_count=len(holdings_df),
        )
        total_value = float(holdings_df.sum().sum())

        return {
            "by_account": self._calculate_by_account(holdings_df),
            "by_account_type": self._calculate_by_account_type(holdings_df),
            "by_asset_class": self._calculate_by_asset_class(holdings_df, total_value),
            "portfolio_summary": self._calculate_portfolio_summary(holdings_df, total_value),
        }

    def _calculate_by_account(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate allocation for each account.

        Returns:
            DataFrame indexed by Account_ID with columns for each asset class:
            - {AssetClass}_dollars: Dollar amount
            - {AssetClass}_pct: Percentage of account
        """
        # Step 1: Sum across securities to get total per Asset Class per Account
        by_asset_class = df.T.groupby(level="Asset_Class").sum().T

        # Step 2: Set index to Account_ID for easier lookup
        if "Account_ID" in by_asset_class.index.names:
            by_asset_class = by_asset_class.reset_index()
            non_numeric_cols = ["Account_Type", "Account_Category", "Account_Name"]
            by_asset_class = by_asset_class.drop(
                columns=[c for c in non_numeric_cols if c in by_asset_class.columns]
            )
            by_asset_class = by_asset_class.set_index("Account_ID")

        # Calculate account totals
        account_totals = by_asset_class.sum(axis=1)

        # Calculate percentages
        percentages = by_asset_class.div(account_totals, axis=0).fillna(0.0) * 100

        # Combine into single DataFrame with MultiIndex columns
        result = pd.concat(
            [by_asset_class.add_suffix("_actual"), percentages.add_suffix("_actual_pct")],
            axis=1,
        )

        # Sort columns
        result = result.reindex(sorted(result.columns), axis=1)

        return result

    def _calculate_by_account_type(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate allocation for each account type.

        Returns:
            DataFrame indexed by Account_Type with dollar and percentage columns.
        """
        # Sum all holdings within each account type
        by_type = df.groupby(level="Account_Type").sum()

        # Group by asset class
        by_asset_class = by_type.T.groupby(level="Asset_Class").sum().T

        # Calculate totals and percentages
        type_totals = by_asset_class.sum(axis=1)
        percentages = by_asset_class.div(type_totals, axis=0).fillna(0.0) * 100

        # Combine
        result = pd.concat(
            [by_asset_class.add_suffix("_actual"), percentages.add_suffix("_actual_pct")],
            axis=1,
        )

        result = result.reindex(sorted(result.columns), axis=1)

        return result

    def _calculate_by_asset_class(
        self,
        df: pd.DataFrame,
        total_value: float,
    ) -> pd.DataFrame:
        """
        Calculate portfolio-wide allocation by asset class.

        Returns:
            DataFrame indexed by asset class with:
            - dollars: Dollar amount
            - percent: Percentage of portfolio
        """
        if total_value == 0:
            return pd.DataFrame(columns=["dollars", "percent"])

        # Sum across all accounts and securities within each asset class
        by_asset_class = df.T.groupby(level="Asset_Class").sum().T

        # Total for each asset class
        totals = by_asset_class.sum(axis=0)

        # Percentages
        percentages = (totals / total_value) * 100

        # Combine into result DataFrame
        result = pd.DataFrame(
            {
                "dollars": totals,
                "percent": percentages,
            }
        )

        return result.sort_values("dollars", ascending=False)

    def _calculate_portfolio_summary(
        self,
        df: pd.DataFrame,
        total_value: float,
    ) -> pd.DataFrame:
        """
        Calculate overall portfolio summary.

        Returns:
            Single-row DataFrame with numeric summary values.
        """
        return pd.DataFrame(
            {
                "total_value": [total_value],
                "num_accounts": [len(df.index)],
                "num_holdings": [(df > 0).sum().sum()],
            }
        )

    def calculate_holdings_detail(
        self,
        holdings_df: pd.DataFrame,
        effective_targets_map: dict[int, dict[str, Decimal]],
    ) -> pd.DataFrame:
        """
        Calculate detailed holdings view with targets and variance.

        Args:
            holdings_df: Long-format DataFrame with columns:
                Account_ID, Asset_Class, Security (or Ticker), Value, Shares, Price
            effective_targets_map: {account_id: {asset_class_name: target_pct}}

        Returns:
            DataFrame with numeric columns: Target_Value, Variance, etc.
        """
        if holdings_df.empty:
            return pd.DataFrame()

        df = holdings_df.copy()

        if "Value" not in df.columns:
            return pd.DataFrame()

        # Ensure Account_ID is a column
        if "Account_ID" not in df.columns and "Account_ID" in df.index.names:
            df = df.reset_index()

        # Calculate Account Totals
        account_totals = df.groupby("Account_ID")["Value"].sum()

        # Determine security column name
        security_col_name = "Ticker" if "Ticker" in df.columns else "Security"

        # Count securities per Asset Class per Account
        sec_counts = df.groupby(["Account_ID", "Asset_Class"])[security_col_name].count()

        # Build targets DataFrame for efficient merging
        target_records = []
        for aid, t_map in effective_targets_map.items():
            for ac, pct in t_map.items():
                target_records.append(
                    {"Account_ID": aid, "Asset_Class": ac, "Target_Pct": float(pct)}
                )

        targets_df = pd.DataFrame(target_records)

        if not targets_df.empty:
            df = df.merge(targets_df, on=["Account_ID", "Asset_Class"], how="left")
        else:
            df["Target_Pct"] = 0.0

        df["Target_Pct"] = df["Target_Pct"].fillna(0.0)

        # Merge counts
        counts_df = sec_counts.reset_index(name="Sec_Count")
        df = df.merge(counts_df, on=["Account_ID", "Asset_Class"], how="left")

        # Merge totals
        totals_df = account_totals.reset_index(name="Account_Total")
        df = df.merge(totals_df, on=["Account_ID"], how="left")

        # Calculate target value and variance
        df["Target_Value"] = df.apply(
            lambda r: (r["Account_Total"] * (r["Target_Pct"] / r["Sec_Count"] / 100.0))
            if r["Sec_Count"] > 0
            else 0.0,
            axis=1,
        )
        df["Value_Variance"] = df["Value"] - df["Target_Value"]

        # Rename Security to Ticker if needed
        if "Security" in df.columns:
            df.rename(columns={"Security": "Ticker"}, inplace=True)

        return df

    def build_holdings_dataframe(self, user: Any, account_id: int | None = None) -> pd.DataFrame:
        """
        Build holdings DataFrame with all necessary metadata for display.

        This method constructs a complete holdings view with account, security,
        and asset class hierarchy information.

        Args:
            user: User object to filter holdings
            account_id: Optional account ID to filter to single account

        Returns:
            DataFrame with columns:
            - Account_ID, Account_Name, Account_Type
            - Asset_Class, Asset_Category, Asset_Group
            - Group_Code, Category_Code
            - Ticker, Security_Name, Shares, Price, Value

            Returns empty DataFrame if no holdings found.
        """
        from portfolio.models import Holding

        # Build query with optimal prefetching
        holdings_qs = Holding.objects.filter(account__user=user)
        if account_id:
            holdings_qs = holdings_qs.filter(account_id=account_id)

        holdings_qs = holdings_qs.select_related(
            "account",
            "account__account_type",
            "account__account_type__group",
            "security",
            "security__asset_class",
            "security__asset_class__category",
            "security__asset_class__category__parent",
        )

        if not holdings_qs.exists():
            return pd.DataFrame()

        # Extract data with complete hierarchy
        data = []
        for h in holdings_qs:
            ac = h.security.asset_class
            category = ac.category if ac else None
            parent = category.parent if category else None

            # Determine hierarchy labels
            if parent:
                group_code = parent.code
                group_label = parent.label
                group_sort_order = parent.sort_order
                category_code = category.code if category else "UNC"
                category_label = category.label if category else "Unclassified"
                category_sort_order = category.sort_order if category else 9999
            elif category:
                group_code = category.code
                group_label = category.label
                group_sort_order = category.sort_order
                category_code = category.code
                category_label = category.label
                category_sort_order = category.sort_order
            else:
                group_code = "UNC"
                group_label = "Unclassified"
                group_sort_order = 9999
                category_code = "UNC"
                category_label = "Unclassified"
                category_sort_order = 9999

            data.append(
                {
                    "Account_ID": h.account_id,
                    "Account_Name": h.account.name,
                    "Account_Type": h.account.account_type.label,
                    "Asset_Class": ac.name if ac else "Unclassified",
                    "Asset_Category": category_label,
                    "Asset_Group": group_label,
                    "Group_Code": group_code,
                    "Group_Sort_Order": group_sort_order,
                    "Category_Code": category_code,
                    "Category_Sort_Order": category_sort_order,
                    "Ticker": h.security.ticker,
                    "Security_Name": h.security.name,
                    "Shares": float(h.shares),
                    "Price": float(h.latest_price) if h.latest_price else 0.0,
                    "Value": float(h.market_value),
                }
            )

        return pd.DataFrame(data)

    def calculate_holdings_with_targets(
        self, user: Any, account_id: int | None = None
    ) -> pd.DataFrame:
        """
        Calculate holdings with target allocations and variances.

        This is the main entry point for holdings view - it builds the complete
        holdings DataFrame with all target calculations.

        Args:
            user: User object
            account_id: Optional account ID to filter to single account

        Returns:
            DataFrame with numeric columns ready for formatting:
            - All columns from build_holdings_dataframe()
            - Target_Shares, Shares_Variance
            - Target_Value, Value_Variance
            - Allocation_Pct, Target_Allocation_Pct, Allocation_Variance_Pct

            Returns empty DataFrame if no holdings.
        """
        # Step 1: Build base holdings DataFrame
        df = self.build_holdings_dataframe(user, account_id)

        if df.empty:
            return df

        # Step 2: Get effective targets for all accounts
        effective_targets_map = self.get_effective_target_map(user)

        # Step 3: Calculate targets using existing method
        # Note: calculate_holdings_detail expects columns: Account_ID, Asset_Class,
        # Ticker (or Security), Value, Shares, Price
        df_with_targets = self.calculate_holdings_detail(df, effective_targets_map)
        # Calculate allocation percentages relative to total value
        total_value = df_with_targets["Value"].sum()
        if total_value > 0:
            df_with_targets["Allocation_Pct"] = (df_with_targets["Value"] / total_value) * 100
            df_with_targets["Target_Allocation_Pct"] = (
                df_with_targets["Target_Value"] / total_value
            ) * 100
        else:
            df_with_targets["Allocation_Pct"] = 0.0
            df_with_targets["Target_Allocation_Pct"] = 0.0
        df_with_targets["Allocation_Variance_Pct"] = (
            df_with_targets["Allocation_Pct"] - df_with_targets["Target_Allocation_Pct"]
        )
        # Calculate Share Targets and Variances
        df_with_targets["Target_Shares"] = df_with_targets.apply(
            lambda r: r["Target_Value"] / r["Price"] if r["Price"] > 0 else 0, axis=1
        )
        df_with_targets["Shares_Variance"] = (
            df_with_targets["Shares"] - df_with_targets["Target_Shares"]
        )

        # Step 4: Sort data for display
        # Priority: Group Order -> Category Order -> Target Value (desc) -> Ticker
        return df_with_targets.sort_values(
            by=["Group_Sort_Order", "Category_Sort_Order", "Target_Value", "Ticker"],
            ascending=[True, True, False, True],
        )

    def build_presentation_dataframe(
        self,
        user: Any,
    ) -> pd.DataFrame:
        """
        Build hierarchical presentation DataFrame with MultiIndex.

        REFACTORED: Eliminates the triple-nested loop with pure pandas operations.

        Returns:
            DataFrame with MultiIndex(group_code, category_code, asset_class_name) and columns:
            - Metadata: group_label, category_label, asset_class_id, row_type, is_*
            - Portfolio:
                portfolio_actual, portfolio_actual_pct,
                portfolio_effective, portfolio_effective_pct,
                portfolio_effective_variance, portfolio_effective_variance_pct
            - Account Types:
                {type_code}_actual, {type_code}_actual_pct,
                {type_code}_policy, {type_code}_policy_pct,
                {type_code}_effective, {type_code}_effective_pct,
                {type_code}_policy_variance, {type_code}_policy_variance_pct,
                {type_code}_effective_variance, {type_code}_effective_variance_pct
            - Accounts:
                {type_code}_{acc_name}_actual, {type_code}_{acc_name}_actual_pct,
                {type_code}_{acc_name}_policy, {type_code}_{acc_name}_policy_pct,
                {type_code}_{acc_name}_policy_variance, {type_code}_{acc_name}_policy_variance_pct

            All values are NUMERIC (no formatting).
        """
        from portfolio.models import Portfolio

        logger.info("building_presentation_dataframe", user_id=user.id)

        # Get holdings DataFrame
        portfolio = Portfolio.objects.filter(user=user).first()
        if not portfolio:
            logger.info("no_portfolio_found", user=user.username)
            return pd.DataFrame()

        holdings_df = portfolio.to_dataframe()
        if holdings_df.empty:
            logger.info("empty_holdings_dataframe")
            return pd.DataFrame()

        logger.info("processing_presentation_data", user=user.username)

        # Step 1: Calculate actual allocations
        allocations = self.calculate_allocations(holdings_df)

        # Step 2: Get metadata
        ac_metadata, hierarchy = self._get_asset_class_metadata(user)
        _account_list, accounts_by_type = self._get_account_metadata(user)
        target_strategies = self._get_target_strategies(user)

        # Step 3: Pre-calculate totals
        portfolio_total = float(allocations["by_asset_class"]["dollars"].sum())
        account_totals = self._calculate_account_totals(allocations, accounts_by_type)

        # Step 4: Build base DataFrame with all asset classes (NO LOOPS)
        df = self._build_asset_class_base_dataframe(ac_metadata, hierarchy)

        # Step 5: Add portfolio calculations (VECTORIZED)
        df = self._add_portfolio_calculations(df, allocations, portfolio_total)

        # Step 6: Add account type calculations (VECTORIZED)
        df = self._add_account_type_calculations(
            df, allocations, accounts_by_type, target_strategies, account_totals
        )

        # Step 7: Add individual account calculations (VECTORIZED)
        df = self._add_account_calculations(
            df, allocations, accounts_by_type, target_strategies, account_totals
        )

        # Step 8: Calculate weighted targets (VECTORIZED)
        df = self._calculate_weighted_targets(df, accounts_by_type, account_totals)

        # Step 9: Calculate portfolio weighted targets (VECTORIZED)
        df = self._calculate_portfolio_weighted_targets(df, accounts_by_type, portfolio_total)

        # Step 10: Calculate portfolio explicit targets (VECTORIZED)
        df = self._calculate_portfolio_explicit_targets(df, target_strategies, portfolio_total)

        # Step 11: Sort the DataFrame
        # Respect sort_order from database if present (non-zero), otherwise fallback to portfolio_effective descending.
        # We use transform to calculate group and category aggregates to ensure assets stay grouped.
        df["group_target_sum"] = df.groupby("group_code")["portfolio_effective"].transform("sum")
        df["cat_target_sum"] = df.groupby(["group_code", "category_code"])[
            "portfolio_effective"
        ].transform("sum")

        # Sorting priority:
        # 1. group_sort_order (ascending)
        # 2. group_target_sum (descending) - fallback for groups
        # 3. category_sort_order (ascending)
        # 4. cat_target_sum (descending) - fallback for categories
        # 5. portfolio_effective (descending) - asset level
        # 6. asset_class_name (ascending) - tie breaker
        df = df.sort_values(
            by=[
                "group_sort_order",
                "group_target_sum",
                "category_sort_order",
                "cat_target_sum",
                "portfolio_effective",
                "asset_class_name",
            ],
            ascending=[True, False, True, False, False, True],
        )

        logger.debug(f"Presentation DataFrame built with {len(df)} rows")

        # Step 10: Set MultiIndex
        df = df.set_index(["group_code", "category_code", "asset_class_name"])

        return df

    def _build_asset_class_base_dataframe(
        self,
        ac_metadata: dict[str, dict[str, Any]],
        hierarchy: dict[str, dict[str, list[str]]],
    ) -> pd.DataFrame:
        """
        Build base DataFrame with all asset classes and metadata.

        Returns:
            DataFrame with columns: group_code, group_label, category_code,
            category_label, asset_class_name, asset_class_id, is_cash, row_type
        """
        rows = []
        for group_code in hierarchy:
            for category_code in hierarchy[group_code]:
                for ac_name in hierarchy[group_code][category_code]:
                    meta = ac_metadata[ac_name]
                    rows.append(
                        {
                            "group_code": group_code,
                            "group_label": meta["group_label"],
                            "group_sort_order": meta["group_sort_order"],
                            "category_code": category_code,
                            "category_label": meta["category_label"],
                            "category_sort_order": meta["category_sort_order"],
                            "asset_class_name": ac_name,
                            "asset_class_id": meta["id"],
                            "is_cash": category_code == "CASH" or ac_name == "Cash",
                            "row_type": "asset",
                        }
                    )

        return pd.DataFrame(rows)

    def _add_portfolio_calculations(
        self,
        df: pd.DataFrame,
        allocations: dict[str, pd.DataFrame],
        portfolio_total: float,
    ) -> pd.DataFrame:
        """
        Add portfolio-level actual allocations using vectorized merge.

        Adds columns: portfolio_actual, portfolio_actual_pct
        """
        df_portfolio = allocations["by_asset_class"]

        # Merge actual values
        df = df.merge(
            df_portfolio[["dollars"]].rename(columns={"dollars": "portfolio_actual"}),
            left_on="asset_class_name",
            right_index=True,
            how="left",
        )
        df["portfolio_actual"] = df["portfolio_actual"].fillna(0.0)

        # Calculate percentages
        df["portfolio_actual_pct"] = (
            df["portfolio_actual"] / portfolio_total * 100 if portfolio_total > 0 else 0.0
        )

        return df

    def _add_account_type_calculations(
        self,
        df: pd.DataFrame,
        allocations: dict[str, pd.DataFrame],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
        account_totals: dict[str, dict[int, float]],
    ) -> pd.DataFrame:
        """
        Add account type columns with actual and policy targets.

        For each account type, adds:
        - {type_code}_actual
        - {type_code}_actual_pct
        - {type_code}_policy
        - {type_code}_policy_pct
        - {type_code}_policy_variance
        - {type_code}_policy_variance_pct
        """
        df_account_type = allocations["by_account_type"]

        for type_id, type_accounts in sorted(accounts_by_type.items()):
            if not type_accounts:
                continue
            type_label = type_accounts[0]["type_label"]
            type_code = type_accounts[0]["type_code"]

            # Extract actual values for this account type
            type_data = {}
            if not df_account_type.empty and type_label in df_account_type.index:
                for ac_name in df["asset_class_name"].unique():
                    col_name = f"{ac_name}_actual"
                    if col_name in df_account_type.columns:
                        type_data[ac_name] = df_account_type.loc[type_label, col_name]

            # Merge actual values
            if type_data:
                type_series = pd.Series(type_data, name=f"{type_code}_actual")
                df = df.merge(
                    type_series,
                    left_on="asset_class_name",
                    right_index=True,
                    how="left",
                )
            else:
                df[f"{type_code}_actual"] = 0.0

            df[f"{type_code}_actual"] = df[f"{type_code}_actual"].fillna(0.0)

            # Calculate actual percentages
            at_total = account_totals["account_type"].get(type_id, 0.0)
            df[f"{type_code}_actual_pct"] = (
                df[f"{type_code}_actual"] / at_total * 100 if at_total > 0 else 0.0
            )

            # Add policy targets (percentages from strategy)
            df[f"{type_code}_policy_pct"] = 0.0
            if type_id in target_strategies.get("account_type", {}):
                type_targets = target_strategies["account_type"][type_id]
                target_map = pd.Series(type_targets)
                df[f"{type_code}_policy_pct"] = (
                    df["asset_class_id"].map(target_map).fillna(0.0).astype(float)
                )

            # Calculate policy targets (dollars)
            df[f"{type_code}_policy"] = df[f"{type_code}_policy_pct"] / 100 * at_total

            # Calculate policy variance
            df[f"{type_code}_policy_variance"] = (
                df[f"{type_code}_actual"] - df[f"{type_code}_policy"]
            )
            df[f"{type_code}_policy_variance_pct"] = (
                df[f"{type_code}_actual_pct"] - df[f"{type_code}_policy_pct"]
            )

        return df

    def _add_account_calculations(
        self,
        df: pd.DataFrame,
        allocations: dict[str, pd.DataFrame],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
        account_totals: dict[str, dict[int, float]],
    ) -> pd.DataFrame:
        """
        Add individual account columns with actual and policy targets.

        For each account, adds:
        - {type_code}_{acc_name}_actual
        - {type_code}_{acc_name}_actual_pct
        - {type_code}_{acc_name}_policy
        - {type_code}_{acc_name}_policy_pct
        - {type_code}_{acc_name}_policy_variance
        - {type_code}_{acc_name}_policy_variance_pct
        """
        df_account = allocations["by_account"]

        for _type_id, type_accounts in sorted(accounts_by_type.items()):
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]

            # Get type policy target for fallback
            at_policy_pct = df[f"{type_code}_policy_pct"]

            for acc_meta in type_accounts:
                acc_id = acc_meta["id"]
                acc_name = acc_meta["name"]
                acc_prefix = f"{type_code}_{acc_name}"

                # Extract actual values
                acc_data = {}
                if not df_account.empty and acc_id in df_account.index:
                    for ac_name in df["asset_class_name"].unique():
                        col_name = f"{ac_name}_actual"
                        if col_name in df_account.columns:
                            acc_data[ac_name] = df_account.loc[acc_id, col_name]

                # Merge actual values
                if acc_data:
                    acc_series = pd.Series(acc_data, name=f"{acc_prefix}_actual")
                    df = df.merge(
                        acc_series,
                        left_on="asset_class_name",
                        right_index=True,
                        how="left",
                    )
                else:
                    df[f"{acc_prefix}_actual"] = 0.0

                df[f"{acc_prefix}_actual"] = df[f"{acc_prefix}_actual"].fillna(0.0)

                # Calculate actual percentages
                acc_total = account_totals["account"].get(acc_id, 0.0)
                df[f"{acc_prefix}_actual_pct"] = (
                    df[f"{acc_prefix}_actual"] / acc_total * 100 if acc_total > 0 else 0.0
                )

                # Add policy targets
                # If account has its own strategy, use it exclusively
                # Otherwise, fall back to account-type strategy
                if acc_id in target_strategies.get("account", {}):
                    # Account has override - use ONLY this strategy
                    acc_targets = target_strategies["account"][acc_id]
                    target_map = pd.Series(acc_targets)
                    df[f"{acc_prefix}_policy_pct"] = (
                        df["asset_class_id"].map(target_map).fillna(0.0)
                    ).astype(float)
                else:
                    # No override - use account-type strategy
                    df[f"{acc_prefix}_policy_pct"] = at_policy_pct

                # Calculate policy targets (dollars)
                df[f"{acc_prefix}_policy"] = df[f"{acc_prefix}_policy_pct"] / 100 * acc_total

                # Calculate policy variance
                df[f"{acc_prefix}_policy_variance"] = (
                    df[f"{acc_prefix}_actual"] - df[f"{acc_prefix}_policy"]
                )
                df[f"{acc_prefix}_policy_variance_pct"] = (
                    df[f"{acc_prefix}_actual_pct"] - df[f"{acc_prefix}_policy_pct"]
                )

        return df

    def _calculate_weighted_targets(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        account_totals: dict[str, dict[int, float]],
    ) -> pd.DataFrame:
        """
        Calculate effective target columns (weighted average) for account types.

        Must be called AFTER _add_account_calculations.

        For each account type, adds:
        - {type_code}_effective
        - {type_code}_effective_pct
        - {type_code}_effective_variance
        - {type_code}_effective_variance_pct
        """
        for type_id, type_accounts in sorted(accounts_by_type.items()):
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]

            # Sum all account policy targets for this type (weighted average)
            effective_target = pd.Series(0.0, index=df.index)

            for acc_meta in type_accounts:
                acc_name = acc_meta["name"]
                acc_prefix = f"{type_code}_{acc_name}"
                effective_target += df[f"{acc_prefix}_policy"]  # Sum dollar policies

            # Calculate Implicit Cash (unassigned value from unassigned accounts or partial strategies)
            at_total = account_totals["account_type"].get(type_id, 0.0)
            assigned_total = float(effective_target.sum())
            unassigned = at_total - assigned_total

            if unassigned > 0.01 and "is_cash" in df.columns:
                # Attribute unassigned value to Cash
                effective_target.loc[df["is_cash"]] += unassigned

            df[f"{type_code}_effective"] = effective_target

            # Calculate effective percentage
            at_total = account_totals["account_type"].get(type_id, 0.0)
            df[f"{type_code}_effective_pct"] = (
                effective_target / at_total * 100 if at_total > 0 else 0.0
            )

            # Calculate effective variance (actual - effective)
            df[f"{type_code}_effective_variance"] = (
                df[f"{type_code}_actual"] - df[f"{type_code}_effective"]
            )
            df[f"{type_code}_effective_variance_pct"] = (
                df[f"{type_code}_actual_pct"] - df[f"{type_code}_effective_pct"]
            )

        return df

    def _calculate_portfolio_weighted_targets(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        portfolio_total: float,
    ) -> pd.DataFrame:
        """
        Calculate portfolio-level effective targets (weighted average).

        Must be called AFTER _calculate_weighted_targets.

        Adds columns:
        - portfolio_effective
        - portfolio_effective_pct
        - portfolio_effective_variance
        - portfolio_effective_variance_pct

        Note: Portfolio level has no policy target (no single portfolio strategy).
        """
        # Sum all account type effective targets
        portfolio_effective = pd.Series(0.0, index=df.index)

        for _type_id, type_accounts in accounts_by_type.items():
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]
            portfolio_effective += df[f"{type_code}_effective"]

        df["portfolio_effective"] = portfolio_effective

        # Calculate percentage
        df["portfolio_effective_pct"] = (
            portfolio_effective / portfolio_total * 100 if portfolio_total > 0 else 0.0
        )

        # Calculate effective variance (actual - effective)
        df["portfolio_effective_variance"] = df["portfolio_actual"] - df["portfolio_effective"]
        df["portfolio_effective_variance_pct"] = (
            df["portfolio_actual_pct"] - df["portfolio_effective_pct"]
        )

        return df

    def _calculate_portfolio_explicit_targets(
        self,
        df: pd.DataFrame,
        target_strategies: dict[str, Any],
        portfolio_total: float,
    ) -> pd.DataFrame:
        """
        Calculate portfolio-level explicit targets.
        """
        explicit_targets = target_strategies.get("portfolio_explicit", {})
        target_map = pd.Series(
            {ac_id: float(pct) for ac_id, pct in explicit_targets.items()}, dtype=float
        )

        df["portfolio_explicit_target_pct"] = (
            df["asset_class_id"].map(target_map).fillna(0.0).astype(float)
        )
        df["portfolio_explicit_target"] = (
            df["portfolio_explicit_target_pct"] / 100 * portfolio_total
        )

        # Calculate policy variance (actual - explicit/policy target)
        df["portfolio_policy_variance"] = df["portfolio_actual"] - df["portfolio_explicit_target"]
        df["portfolio_policy_variance_pct"] = (
            df["portfolio_actual_pct"] - df["portfolio_explicit_target_pct"]
        )

        return df

    def aggregate_presentation_levels(
        self,
        df: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        """
        Calculate all aggregation levels using pandas groupby.

        REFACTORED: Eliminates all manual loops using vectorized operations.

        Args:
            df: Asset-level DataFrame from build_presentation_dataframe()

        Returns:
            Dict with DataFrames for each aggregation level:
            - 'assets': Original asset-level data
            - 'category_subtotals': Aggregated by category
            - 'group_totals': Aggregated by group
            - 'grand_total': Total across everything

            All DataFrames have the same column structure with numeric values.
        """
        if df.empty:
            return {
                "assets": df,
                "category_subtotals": pd.DataFrame(),
                "group_totals": pd.DataFrame(),
                "grand_total": pd.DataFrame(),
            }

        # Get numeric columns (exclude metadata)
        numeric_cols = [
            col
            for col in df.columns
            if not col.startswith(("group_", "category_", "asset_class_", "row_", "is_"))
        ]

        # Category subtotals: group by first two index levels
        category_counts = df.groupby(level=["group_code", "category_code"], sort=False).size()
        category_subtotals = (
            df[numeric_cols].groupby(level=["group_code", "category_code"], sort=False).sum()
        )

        # Filter redundant categories (only 1 asset)
        non_redundant_categories = category_counts[category_counts > 1].index
        category_subtotals = category_subtotals.loc[non_redundant_categories]

        # Add metadata (VECTORIZED - NO LOOP)
        if not category_subtotals.empty:
            metadata_cols = ["group_label", "category_label", "group_code", "category_code"]
            # Filter to only existing columns to avoid KeyError (some might be in index)
            existing_meta = [c for c in metadata_cols if c in df.columns]
            category_metadata = (
                df[existing_meta].groupby(level=["group_code", "category_code"], sort=False).first()
            )
            category_subtotals = category_subtotals.join(category_metadata)
            category_subtotals["row_type"] = "subtotal"

        # Group totals: group by first index level only
        group_counts = df.groupby(level="group_code", sort=False).size()
        group_totals = df[numeric_cols].groupby(level="group_code", sort=False).sum()

        # Filter redundant groups (only 1 asset child)
        non_redundant_groups = group_counts[group_counts > 1].index
        group_totals = group_totals.loc[non_redundant_groups]

        # Add metadata (VECTORIZED - NO LOOP)
        if not group_totals.empty:
            metadata_cols = ["group_label", "group_code"]
            existing_meta = [c for c in metadata_cols if c in df.columns]
            group_metadata = df[existing_meta].groupby(level="group_code", sort=False).first()
            group_totals = group_totals.join(group_metadata)
            group_totals["row_type"] = "group_total"

        # Grand total: sum all numeric columns
        grand_total = df[numeric_cols].sum().to_frame().T
        grand_total["row_type"] = "grand_total"
        grand_total.index = ["TOTAL"]

        aggregated = {
            "assets": df,
            "category_subtotals": category_subtotals,
            "group_totals": group_totals,
            "grand_total": grand_total,
        }

        # ADD: Calculate variance columns for all DataFrames
        for _df_name, df_data in aggregated.items():
            if not df_data.empty:
                # Portfolio variances
                if "portfolio_effective" in df_data.columns:
                    df_data["portfolio_effective_variance"] = (
                        df_data["portfolio_actual"] - df_data["portfolio_effective"]
                    )
                    df_data["portfolio_effective_variance_pct"] = (
                        df_data["portfolio_actual_pct"] - df_data["portfolio_effective_pct"]
                    )

                # Policy variances (if policy columns exist)
                if "portfolio_explicit_target" in df_data.columns:
                    df_data["portfolio_policy_variance"] = (
                        df_data["portfolio_actual"] - df_data["portfolio_explicit_target"]
                    )
                    df_data["portfolio_policy_variance_pct"] = (
                        df_data["portfolio_actual_pct"] - df_data["portfolio_explicit_target_pct"]
                    )

                # Account-level variances (for each account/type column)
                # Pattern: {prefix}_actual vs {prefix}_effective or {prefix}_policy
                for col in df_data.columns:
                    if col.endswith("_actual"):
                        prefix = col[:-7]  # Remove '_actual'

                        # Effective Variance (for Accounts and Account Types)
                        effective_col = f"{prefix}_effective"
                        if effective_col in df_data.columns:
                            df_data[f"{prefix}_variance"] = df_data[col] - df_data[effective_col]
                            # Percentage variance
                            actual_pct_col = f"{prefix}_actual_pct"
                            effective_pct_col = f"{prefix}_effective_pct"
                            if (
                                actual_pct_col in df_data.columns
                                and effective_pct_col in df_data.columns
                            ):
                                df_data[f"{prefix}_variance_pct"] = (
                                    df_data[actual_pct_col] - df_data[effective_pct_col]
                                )

                        # Policy Variance (already calculated in _add_account_calculations but ensuring it exists for aggregates)
                        # Actually, policy variance is linearly additive ($), but percentages are not additive in the same way?
                        # Wait, aggregation logic:
                        # Sum of (Actual - Policy) for assets should equal (Sum Actions - Sum Policy) for subtotal.
                        # Since we summed `_actual` and `_policy` columns, we can just recalculate the difference.
                        policy_col = f"{prefix}_policy"
                        if policy_col in df_data.columns:
                            df_data[f"{prefix}_policy_variance"] = (
                                df_data[col] - df_data[policy_col]
                            )
                            # Percentage variance recalculation for aggregates
                            actual_pct_col = f"{prefix}_actual_pct"
                            policy_pct_col = f"{prefix}_policy_pct"
                            if (
                                actual_pct_col in df_data.columns
                                and policy_pct_col in df_data.columns
                            ):
                                df_data[f"{prefix}_policy_variance_pct"] = (
                                    df_data[actual_pct_col] - df_data[policy_pct_col]
                                )

        return aggregated

    def _calculate_account_totals(
        self,
        allocations: dict[str, pd.DataFrame],
        accounts_by_type: dict[int, list[dict[str, Any]]],
    ) -> dict[str, dict[int, float]]:
        """
        Pre-calculate account and account type totals.

        Returns:
            {
                'account': {account_id: total_value},
                'account_type': {type_id: total_value}
            }
        """
        df_account = allocations["by_account"]
        df_account_type = allocations["by_account_type"]

        account_totals = {}
        if not df_account.empty:
            dollar_cols = [c for c in df_account.columns if c.endswith("_actual")]
            account_totals = df_account[dollar_cols].sum(axis=1).to_dict()

        account_type_totals = {}
        if not df_account_type.empty:
            dollar_cols = [c for c in df_account_type.columns if c.endswith("_actual")]
            type_label_totals = df_account_type[dollar_cols].sum(axis=1).to_dict()

            # Map type_id to its total value
            for tid, accs in accounts_by_type.items():
                if accs:
                    label = accs[0]["type_label"]
                    account_type_totals[tid] = type_label_totals.get(label, 0.0)

        return {
            "account": account_totals,
            "account_type": account_type_totals,
        }

    def get_effective_target_map(self, user: Any) -> dict[int, dict[str, Decimal]]:
        """
        Get map of {account_id: {asset_class_name: target_pct}}.

        Uses Account domain method for cleaner code.

        Used by HoldingsView and calculate_holdings_detail.
        """
        from portfolio.models import Account

        # Use Account domain method - much simpler!
        accounts = (
            Account.objects.filter(user=user)
            .select_related(
                "account_type",
                "allocation_strategy",
                "portfolio__allocation_strategy",
            )
            .prefetch_related("allocation_strategy__target_allocations__asset_class")
        )

        return {account.id: account.get_target_allocations_by_name() for account in accounts}

    def _get_asset_class_metadata(
        self,
        user: Any,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, list[str]]]]:
        """
        Gather asset class hierarchy metadata.

        Returns:
            (ac_metadata, hierarchy)
        """
        from collections import defaultdict

        from portfolio.models import AssetClass

        asset_classes = AssetClass.objects.select_related("category", "category__parent").order_by(
            "category__parent__sort_order", "category__sort_order", "name"
        )

        ac_metadata = {}
        hierarchy: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        for ac in asset_classes:
            if ac.category.parent:
                group_code = ac.category.parent.code
                group_label = ac.category.parent.label
                group_sort_order = ac.category.parent.sort_order
            else:
                group_code = ac.category.code
                group_label = ac.category.label
                group_sort_order = ac.category.sort_order

            cat_code = ac.category.code
            cat_label = ac.category.label
            cat_sort_order = ac.category.sort_order

            ac_metadata[ac.name] = {
                "id": ac.id,
                "group_code": group_code,
                "group_label": group_label,
                "group_sort_order": group_sort_order,
                "category_code": cat_code,
                "category_label": cat_label,
                "category_sort_order": cat_sort_order,
            }

            hierarchy[group_code][cat_code].append(ac.name)

        return ac_metadata, dict(hierarchy)

    def _get_account_metadata(
        self,
        user: Any,
    ) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
        """
        Gather account metadata organized by account type.

        Returns:
            (account_list, accounts_by_type)
        """
        from collections import defaultdict

        from portfolio.models import Account

        accounts = (
            Account.objects.filter(user=user)
            .select_related("account_type")
            .order_by("account_type__group__sort_order", "account_type__label", "name")
        )

        account_list = []
        accounts_by_type: dict[int, list[dict[str, Any]]] = defaultdict(list)

        for acc in accounts:
            acc_dict = {
                "id": acc.id,
                "name": acc.name,
                "type_id": acc.account_type_id,
                "type_label": acc.account_type.label,
                "type_code": acc.account_type.code,
            }
            account_list.append(acc_dict)
            accounts_by_type[acc.account_type_id].append(acc_dict)

        return account_list, dict(accounts_by_type)

    def _get_target_strategies(
        self,
        user: Any,
    ) -> dict[str, Any]:
        """
        Gather target allocation strategies.

        Returns:
            {
                'account_type': {type_id: {ac_id: target_pct}},
                'account': {account_id: {ac_id: target_pct}},
                'at_strategy_map': {type_id: strategy_id},
                'acc_strategy_map': {account_id: strategy_id},
                'portfolio_explicit': {ac_id: target_pct}
            }
        """
        from collections import defaultdict

        from portfolio.models import (
            Account,
            AccountTypeStrategyAssignment,
            Portfolio,
            TargetAllocation,
        )

        result: dict[str, Any] = {
            "account_type": {},
            "account": {},
            "at_strategy_map": {},
            "acc_strategy_map": {},
            "portfolio_explicit": {},
        }

        # 1. Gather all relevant strategy IDs
        strategy_ids: set[int] = set()

        # Portfolio level strategy
        portfolio = (
            Portfolio.objects.filter(user=user).select_related("allocation_strategy").first()
        )
        portfolio_strategy_id = None
        if portfolio and portfolio.allocation_strategy_id:
            portfolio_strategy_id = portfolio.allocation_strategy_id
            strategy_ids.add(portfolio_strategy_id)

        # Account Type assignments
        at_assignments = AccountTypeStrategyAssignment.objects.filter(user=user).select_related(
            "allocation_strategy"
        )
        at_strategy_map = {}
        for assignment in at_assignments:
            at_strategy_map[assignment.account_type_id] = assignment.allocation_strategy_id
            strategy_ids.add(assignment.allocation_strategy_id)

        # Account-level overrides
        accounts = Account.objects.filter(
            user=user, allocation_strategy_id__isnull=False
        ).select_related("allocation_strategy")
        acc_strategy_map = {}
        for acc in accounts:
            if acc.allocation_strategy_id:
                acc_strategy_map[acc.id] = acc.allocation_strategy_id
                strategy_ids.add(acc.allocation_strategy_id)

        # 2. Fetch all target allocations for these strategies
        target_allocations = TargetAllocation.objects.filter(
            strategy_id__in=strategy_ids
        ).select_related("asset_class")

        # Build map: strategy_id -> {ac_id: target_pct}
        strategy_targets: dict[int, dict[int, Decimal]] = defaultdict(dict)
        for ta in target_allocations:
            strategy_targets[ta.strategy_id][ta.asset_class_id] = ta.target_percent

        # 3. Map targets to the result structure
        if portfolio_strategy_id:
            result["portfolio_explicit"] = strategy_targets.get(portfolio_strategy_id, {})

        # Map to account types
        for at_id, strategy_id in at_strategy_map.items():
            result["account_type"][at_id] = strategy_targets.get(strategy_id, {})

        # Map to accounts
        for acc_id, strategy_id in acc_strategy_map.items():
            result["account"][acc_id] = strategy_targets.get(strategy_id, {})

        result["at_strategy_map"] = at_strategy_map
        result["acc_strategy_map"] = acc_strategy_map

        return result

    def calculate_account_variances(self, user: Any) -> dict[int, float]:
        """
        Calculate absolute deviation variance percentage for each account.

        Uses Account domain model method for consistency and DRY principle.

        Returns:
            Dict of {account_id: variance_pct}
        """
        from portfolio.domain.allocation import AssetAllocation
        from portfolio.models import Account

        variances = {}

        accounts = (
            Account.objects.filter(user=user)
            .select_related(
                "account_type",
                "allocation_strategy",
                "portfolio",
            )
            .prefetch_related(
                "holdings__security__asset_class",
                "allocation_strategy__target_allocations__asset_class",
            )
        )

        for account in accounts:
            # Get effective strategy for this account
            strategy = account.get_effective_allocation_strategy()
            if not strategy:
                continue

            # Convert TargetAllocations to AssetAllocation domain objects
            allocations = [
                AssetAllocation(
                    asset_class_name=ta.asset_class.name,
                    target_pct=ta.target_percent,
                )
                for ta in strategy.target_allocations.all()
            ]

            # Use Account domain method - single source of truth
            account_total = account.total_value()
            if account_total == Decimal("0.00"):
                # Empty account with targets = 100% variance
                variance_pct = float(sum(a.target_pct for a in allocations))
            else:
                # Calculate deviation using domain model
                deviation = account.calculate_deviation_from_allocations(allocations)
                variance_pct = float(deviation / account_total * 100)

            variances[account.id] = variance_pct

        return variances

    def get_account_totals(self, user: Any) -> dict[int, Decimal]:
        """
        Get current total value for all user accounts.

        Efficient extraction using pandas aggregation on holdings DataFrame.
        This is the authoritative source for account totals used across the application.

        Performance: O(H) where H = total holdings (single pandas groupby)
        vs. O(N*H) for iterating accounts calling total_value()

        Args:
            user: User object to get accounts for

        Returns:
            Dict of {account_id: total_value_as_Decimal}
            Returns empty dict if user has no holdings

        Example:
            >>> engine = AllocationCalculationEngine()
            >>> totals = engine.get_account_totals(user)
            >>> totals
            {1: Decimal('50000.00'), 2: Decimal('75000.00')}
        """
        # Build holdings DataFrame (reuses existing efficient query)
        df = self._build_holdings_dataframe(user)

        if df.empty:
            return {}

        # Pandas vectorized aggregation - much faster than Python loops
        account_totals = df.groupby(level="Account_ID")["Value"].sum()

        # Convert to Decimal for consistency with domain models
        return {
            int(account_id): Decimal(str(total)) for account_id, total in account_totals.items()
        }

    def get_portfolio_total(self, user: Any) -> Decimal:
        """
        Get total portfolio value across all accounts.

        Args:
            user: User object

        Returns:
            Total portfolio value as Decimal
        """
        account_totals = self.get_account_totals(user)
        return sum(account_totals.values(), Decimal("0.00"))

    def _build_holdings_dataframe(self, user: Any) -> pd.DataFrame:
        """
        Build a flat DataFrame of holdings for the user.
        Exposed internally to support different aggregation types.
        """
        from portfolio.models import Holding

        holdings = Holding.objects.filter(account__user=user).select_related(
            "account", "security__asset_class"
        )

        if not holdings.exists():
            return pd.DataFrame()

        data = []
        for h in holdings:
            price = h.latest_price or 0
            value = float(h.shares * price)
            data.append(
                {
                    "Account_ID": h.account_id,
                    "Asset_Class": h.security.asset_class.name
                    if h.security.asset_class
                    else "Unclassified",
                    "Value": value,
                }
            )

        df = pd.DataFrame(data)
        df = df.set_index(["Account_ID", "Asset_Class"])
        return df

    def _empty_allocations(self) -> dict[str, pd.DataFrame]:
        """Return empty DataFrames for empty portfolio."""
        return {
            "by_account": pd.DataFrame(),
            "by_account_type": pd.DataFrame(),
            "by_asset_class": pd.DataFrame(),
            "portfolio_summary": pd.DataFrame(),
        }

    # ========================================================================
    # PRESENTATION FORMATTING (formerly AllocationPresentationFormatter)
    # ========================================================================

    def get_presentation_rows(self, user: Any) -> list[dict[str, Any]]:
        """
        Calculate and format allocation data for dashboard/targets views.

        This is the primary API method for allocation presentation.
        """
        logger.info("building_presentation_rows", user_id=user.id)

        # Step 1: Build numeric DataFrame
        df = self.build_presentation_dataframe(user=user)
        if df.empty:
            logger.info("no_holdings_for_presentation", user_id=user.id)
            return []

        # Step 2: Aggregate at all levels (includes variance calculations)
        aggregated = self.aggregate_presentation_levels(df)

        # Step 3: Format for display
        _, accounts_by_type = self._get_account_metadata(user)
        strategies = self._get_target_strategies(user)

        return self._format_presentation_rows(
            aggregated_data=aggregated,
            accounts_by_type=accounts_by_type,
            target_strategies=strategies,
        )

    def get_holdings_rows(self, user: Any, account_id: int | None = None) -> list[dict[str, Any]]:
        """
        Calculate and format holdings data for holdings view.
        """
        logger.info(
            "building_holdings_rows",
            user_id=user.id,
            account_id=account_id,
        )

        # Step 1: Calculate holdings with targets
        holdings_df = self.calculate_holdings_with_targets(user, account_id)
        if holdings_df.empty:
            logger.info(
                "no_holdings_found",
                user_id=user.id,
                account_id=account_id,
            )
            return []

        # Step 2: Format for display
        return self._format_holdings_rows(holdings_df)

    def _format_presentation_rows(
        self,
        aggregated_data: dict[str, pd.DataFrame],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
    ) -> list[dict[str, Any]]:
        logger.info("formatting_presentation_rows")
        """
        Format aggregated numeric DataFrames into display-ready rows.
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
                            # Use Calculated Column if exists, else fallback to naive calculation (legacy compat)
                            row.get(f"{acc_prefix}_policy_variance_pct")
                            or (
                                row.get(f"{acc_prefix}_actual_pct", 0.0)
                                - row.get(f"{acc_prefix}_policy_pct", 0.0)
                            )
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

    def _format_holdings_rows(
        self,
        holdings_df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """
        Format holdings DataFrame into display-ready rows with aggregations.
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
                    "account_id": int(row["Account_ID"]),  # Ensure int
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

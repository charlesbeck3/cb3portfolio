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


class AllocationCalculationEngine:
    """
    Calculate portfolio allocations at all hierarchy levels using pandas.

    All methods return DataFrames with raw numeric values.
    Views/templates are responsible for formatting display strings.
    """

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
            return self._empty_allocations()

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
            [by_asset_class.add_suffix("_dollars"), percentages.add_suffix("_pct")],
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
            [by_asset_class.add_suffix("_dollars"), percentages.add_suffix("_pct")],
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
                category_code = category.code if category else "UNC"
                category_label = category.label if category else "Unclassified"
            elif category:
                group_code = category.code
                group_label = category.label
                category_code = category.code
                category_label = category.label
            else:
                group_code = "UNC"
                group_label = "Unclassified"
                category_code = "UNC"
                category_label = "Unclassified"

            data.append({
                "Account_ID": h.account_id,
                "Account_Name": h.account.name,
                "Account_Type": h.account.account_type.label,
                "Asset_Class": ac.name if ac else "Unclassified",
                "Asset_Category": category_label,
                "Asset_Group": group_label,
                "Group_Code": group_code,
                "Category_Code": category_code,
                "Ticker": h.security.ticker,
                "Security_Name": h.security.name,
                "Shares": float(h.shares),
                "Price": float(h.current_price) if h.current_price else 0.0,
                "Value": float(h.market_value),
            })

        return pd.DataFrame(data)

    def calculate_holdings_with_targets(
        self,
        user: Any,
        account_id: int | None = None
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
            df_with_targets["Target_Allocation_Pct"] = (df_with_targets["Target_Value"] / total_value) * 100
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
        df_with_targets["Shares_Variance"] = df_with_targets["Shares"] - df_with_targets["Target_Shares"]

        return df_with_targets

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
            - Portfolio: portfolio_current, portfolio_target, portfolio_variance
            - Account Types: {type_code}_current, {type_code}_target, {type_code}_variance
            - Accounts: {type_code}_{acc_name}_current, {type_code}_{acc_name}_target, etc.

            All values are NUMERIC (no formatting).
        """
        from portfolio.models import Portfolio

        # Get holdings DataFrame
        portfolio = Portfolio.objects.filter(user=user).first()
        if not portfolio:
            return pd.DataFrame()

        holdings_df = portfolio.to_dataframe()
        if holdings_df.empty:
            return pd.DataFrame()

        # Step 1: Calculate current allocations
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

        # Step 9.5: Sort the DataFrame
        # Respect sort_order from database if present (non-zero), otherwise fallback to portfolio_target descending.
        # We use transform to calculate group and category aggregates to ensure assets stay grouped.
        df["group_target_sum"] = df.groupby("group_code")["portfolio_target"].transform("sum")
        df["cat_target_sum"] = df.groupby(["group_code", "category_code"])[
            "portfolio_target"
        ].transform("sum")

        # Sorting priority:
        # 1. group_sort_order (ascending)
        # 2. group_target_sum (descending) - fallback for groups
        # 3. category_sort_order (ascending)
        # 4. cat_target_sum (descending) - fallback for categories
        # 5. portfolio_target (descending) - asset level
        # 6. asset_class_name (ascending) - tie breaker
        df = df.sort_values(
            by=[
                "group_sort_order",
                "group_target_sum",
                "category_sort_order",
                "cat_target_sum",
                "portfolio_target",
                "asset_class_name",
            ],
            ascending=[True, False, True, False, False, True],
        )

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
        Add portfolio-level current/target/variance columns using vectorized merge.

        Adds columns: portfolio_current, portfolio_current_pct
        """
        df_portfolio = allocations["by_asset_class"]

        # Merge current values
        df = df.merge(
            df_portfolio[["dollars"]].rename(columns={"dollars": "portfolio_current"}),
            left_on="asset_class_name",
            right_index=True,
            how="left",
        )
        df["portfolio_current"] = df["portfolio_current"].fillna(0.0)

        # Calculate percentages
        df["portfolio_current_pct"] = (
            df["portfolio_current"] / portfolio_total * 100 if portfolio_total > 0 else 0.0
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
        Add account type columns using vectorized operations.

        For each account type, adds:
        - {type_code}_current
        - {type_code}_current_pct
        - {type_code}_target_input
        """
        df_account_type = allocations["by_account_type"]

        for type_id, type_accounts in sorted(accounts_by_type.items()):
            if not type_accounts:
                continue
            type_label = type_accounts[0]["type_label"]
            type_code = type_accounts[0]["type_code"]

            # Extract current values for this account type
            type_data = {}
            if not df_account_type.empty and type_label in df_account_type.index:
                for ac_name in df["asset_class_name"].unique():
                    col_name = f"{ac_name}_dollars"
                    if col_name in df_account_type.columns:
                        type_data[ac_name] = df_account_type.loc[type_label, col_name]

            # Create temporary series and merge
            if type_data:
                type_series = pd.Series(type_data, name=f"{type_code}_current")
                df = df.merge(
                    type_series,
                    left_on="asset_class_name",
                    right_index=True,
                    how="left",
                )
            else:
                df[f"{type_code}_current"] = 0.0

            df[f"{type_code}_current"] = df[f"{type_code}_current"].fillna(0.0)

            # Calculate percentages
            at_total = account_totals["account_type"].get(type_id, 0.0)
            df[f"{type_code}_current_pct"] = (
                df[f"{type_code}_current"] / at_total * 100 if at_total > 0 else 0.0
            )

            # Add target inputs
            df[f"{type_code}_target_input"] = 0.0
            if type_id in target_strategies.get("account_type", {}):
                type_targets = target_strategies["account_type"][type_id]
                target_map = pd.Series(type_targets)
                df[f"{type_code}_target_input"] = (
                    df["asset_class_id"].map(target_map).fillna(0.0).astype(float)
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
        Add individual account columns using vectorized operations.

        For each account, adds:
        - {type_code}_{acc_name}_current
        - {type_code}_{acc_name}_current_pct
        - {type_code}_{acc_name}_target
        - {type_code}_{acc_name}_target_pct
        - {type_code}_{acc_name}_variance
        """
        df_account = allocations["by_account"]

        for _type_id, type_accounts in sorted(accounts_by_type.items()):
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]

            # Get type target input for fallback
            at_target_input = df[f"{type_code}_target_input"]

            for acc_meta in type_accounts:
                acc_id = acc_meta["id"]
                acc_name = acc_meta["name"]
                acc_prefix = f"{type_code}_{acc_name}"

                # Extract current values
                acc_data = {}
                if not df_account.empty and acc_id in df_account.index:
                    for ac_name in df["asset_class_name"].unique():
                        col_name = f"{ac_name}_dollars"
                        if col_name in df_account.columns:
                            acc_data[ac_name] = df_account.loc[acc_id, col_name]

                # Merge
                if acc_data:
                    acc_series = pd.Series(acc_data, name=f"{acc_prefix}_current")
                    df = df.merge(
                        acc_series,
                        left_on="asset_class_name",
                        right_index=True,
                        how="left",
                    )
                else:
                    df[f"{acc_prefix}_current"] = 0.0

                df[f"{acc_prefix}_current"] = df[f"{acc_prefix}_current"].fillna(0.0)

                # Calculate percentages
                acc_total = account_totals["account"].get(acc_id, 0.0)
                df[f"{acc_prefix}_current_pct"] = (
                    df[f"{acc_prefix}_current"] / acc_total * 100 if acc_total > 0 else 0.0
                )

                # Add targets
                df[f"{acc_prefix}_target_pct"] = at_target_input

                if acc_id in target_strategies.get("account", {}):
                    acc_targets = target_strategies["account"][acc_id]
                    target_map = pd.Series(acc_targets)
                    # Override with account-specific target if exists
                    df[f"{acc_prefix}_target_pct"] = (
                        df["asset_class_id"].map(target_map).fillna(df[f"{acc_prefix}_target_pct"])
                    ).astype(float)

                df[f"{acc_prefix}_target"] = df[f"{acc_prefix}_target_pct"] / 100 * acc_total

                # Calculate variance
                df[f"{acc_prefix}_variance"] = (
                    df[f"{acc_prefix}_current"] - df[f"{acc_prefix}_target"]
                )

        return df

    def _calculate_weighted_targets(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        account_totals: dict[str, dict[int, float]],
    ) -> pd.DataFrame:
        """
        Calculate weighted target columns for account types.

        Must be called AFTER _add_account_calculations.
        """
        for type_id, type_accounts in sorted(accounts_by_type.items()):
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]

            # Sum all account targets for this type
            weighted_target = pd.Series(0.0, index=df.index)

            for acc_meta in type_accounts:
                acc_name = acc_meta["name"]
                acc_prefix = f"{type_code}_{acc_name}"
                weighted_target += df[f"{acc_prefix}_target"]

            df[f"{type_code}_weighted_target"] = weighted_target

            # Calculate weighted percentage
            at_total = account_totals["account_type"].get(type_id, 0.0)
            df[f"{type_code}_weighted_target_pct"] = (
                weighted_target / at_total * 100 if at_total > 0 else 0.0
            )

            # Calculate variance
            df[f"{type_code}_variance"] = df[f"{type_code}_current"] - weighted_target
            # Calculate variance percentage
            df[f"{type_code}_variance_pct"] = (
                df[f"{type_code}_current_pct"] - df[f"{type_code}_weighted_target_pct"]
            )

        return df

    def _calculate_portfolio_weighted_targets(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        portfolio_total: float,
    ) -> pd.DataFrame:
        """
        Calculate portfolio-level weighted targets.

        Must be called AFTER _calculate_weighted_targets.
        """
        # Sum all account type weighted targets
        portfolio_target = pd.Series(0.0, index=df.index)

        for _type_id, type_accounts in accounts_by_type.items():
            if not type_accounts:
                continue
            type_code = type_accounts[0]["type_code"]
            portfolio_target += df[f"{type_code}_weighted_target"]

        df["portfolio_target"] = portfolio_target

        # Calculate percentage
        df["portfolio_target_pct"] = (
            portfolio_target / portfolio_total * 100 if portfolio_total > 0 else 0.0
        )

        # Calculate variance
        df["portfolio_variance"] = df["portfolio_current"] - portfolio_target
        df["portfolio_variance_pct"] = df["portfolio_current_pct"] - df["portfolio_target_pct"]

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

        return {
            "assets": df,
            "category_subtotals": category_subtotals,
            "group_totals": group_totals,
            "grand_total": grand_total,
        }

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
            dollar_cols = [c for c in df_account.columns if c.endswith("_dollars")]
            account_totals = df_account[dollar_cols].sum(axis=1).to_dict()

        account_type_totals = {}
        if not df_account_type.empty:
            dollar_cols = [c for c in df_account_type.columns if c.endswith("_dollars")]
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
                'acc_strategy_map': {account_id: strategy_id}
            }
        """
        from collections import defaultdict

        from portfolio.models import (
            Account,
            AccountTypeStrategyAssignment,
            TargetAllocation,
        )

        result: dict[str, Any] = {
            "account_type": {},
            "account": {},
            "at_strategy_map": {},
            "acc_strategy_map": {},
        }

        # Account Type assignments
        at_assignments = AccountTypeStrategyAssignment.objects.filter(user=user).select_related(
            "allocation_strategy"
        )

        strategy_ids: set[int] = set()
        at_strategy_map = {}

        for assignment in at_assignments:
            at_strategy_map[assignment.account_type_id] = assignment.allocation_strategy_id
            strategy_ids.add(assignment.allocation_strategy_id)

        # Account-level overrides
        accounts = Account.objects.filter(
            user=user, allocation_strategy__isnull=False
        ).select_related("allocation_strategy")

        acc_strategy_map = {}
        for acc in accounts:
            if acc.allocation_strategy_id:
                acc_strategy_map[acc.id] = acc.allocation_strategy_id
                strategy_ids.add(acc.allocation_strategy_id)

        # Fetch all target allocations
        target_allocations = TargetAllocation.objects.filter(
            strategy_id__in=strategy_ids
        ).select_related("asset_class")

        # Build map: strategy_id -> {ac_id: target_pct}
        strategy_targets: dict[int, dict[int, Decimal]] = defaultdict(dict)
        for ta in target_allocations:
            strategy_targets[ta.strategy_id][ta.asset_class_id] = ta.target_percent

        # Cash allocations are already stored in TargetAllocation table via
        # AllocationStrategy.save_allocations() domain model.
        # Add defensive validation to catch data integrity issues.
        import logging

        logger = logging.getLogger(__name__)

        for strat_id in strategy_ids:
            targets = strategy_targets[strat_id]
            total = sum(targets.values())

            # Validate database has complete allocations (should sum to ~100%)
            if abs(total - Decimal("100.0")) > Decimal("0.1"):
                logger.warning(
                    f"Strategy {strat_id} allocations sum to {total}%, expected ~100%. "
                    f"Data integrity issue - strategy may need to be re-saved."
                )

        # Map to account types
        for at_id, strategy_id in at_strategy_map.items():
            result["account_type"][at_id] = strategy_targets.get(strategy_id, {})

        # Map to accounts
        for acc_id, strategy_id in acc_strategy_map.items():
            result["account"][acc_id] = strategy_targets.get(strategy_id, {})

        result["at_strategy_map"] = at_strategy_map
        result["acc_strategy_map"] = acc_strategy_map

        return result

    def calculate_account_drifts(self, user: Any) -> dict[int, float]:
        """
        Calculate absolute deviation drift percentage for each account.

        Uses Account domain model method for consistency and DRY principle.

        Returns:
            Dict of {account_id: drift_pct}
        """
        from portfolio.domain.allocation import AssetAllocation
        from portfolio.models import Account

        drifts = {}

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
                # Empty account with targets = 100% drift
                drift_pct = float(sum(a.target_pct for a in allocations))
            else:
                # Calculate deviation using domain model
                deviation = account.calculate_deviation_from_allocations(allocations)
                drift_pct = float(deviation / account_total * 100)

            drifts[account.id] = drift_pct

        return drifts

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

        holdings = (
            Holding.objects.filter(account__user=user)
            .select_related("account", "security__asset_class")
            .values(
                "account_id",
                "security__asset_class__name",
                "shares",
                "current_price",
            )
        )

        if not holdings:
            return pd.DataFrame()

        data = []
        for h in holdings:
            price = h["current_price"] or 0
            value = float(h["shares"] * price)
            data.append(
                {
                    "Account_ID": h["account_id"],
                    "Asset_Class": h["security__asset_class__name"],
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

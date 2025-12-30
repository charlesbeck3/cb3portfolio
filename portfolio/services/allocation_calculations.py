"""
Pure pandas-based allocation calculations using MultiIndex DataFrames.
Zero Django dependencies - can be tested with mock DataFrames.

DESIGN PHILOSOPHY:
- Store ONLY numeric values in DataFrames (no formatting)
- Use MultiIndex for natural hierarchy representation
- Single aggregation pattern using pandas groupby
- Formatting happens in views/templates, not here
"""

from collections import OrderedDict
from decimal import Decimal
from typing import Any, cast

from django.db import connection

import pandas as pd
import structlog

# Opt-in to future downcasting behavior to suppress FutureWarnings from fillna()
# that would previously downcast object-dtype arrays silently.
pd.set_option("future.no_silent_downcasting", True)

logger = structlog.get_logger(__name__)


class AllocationCalculationEngine:
    """
    Calculate portfolio allocations at all hierarchy levels using pandas.

    All methods return DataFrames with raw numeric values.
    Views/templates are responsible for formatting display strings.
    """

    def __init__(self) -> None:
        logger.debug("initializing_allocation_engine")

    def get_sidebar_data(self, user: Any) -> dict[str, Any]:
        """
        Get all sidebar data in a single optimized call.

        This method consolidates multiple queries and calculations into an
        efficient batch operation, reducing round-trips to the database.

        Args:
            user: User to get sidebar data for

        Returns:
            dict with:
                - grand_total: Total portfolio value (Decimal)
                - account_totals: {account_id: total_value} (dict)
                - account_variances: {account_id: variance_pct} (dict)
                - accounts_by_group: {group_name: [account_data...]} (OrderedDict)
                - query_count: Number of database queries executed (for monitoring)
        """
        from django.conf import settings

        from portfolio.models import (
            Account,
            AccountGroup,
            AccountTypeStrategyAssignment,
            AllocationStrategy,
            Portfolio,
        )

        logger.info("building_sidebar_data", user_id=user.id)

        # Track query count for monitoring (only in DEBUG mode)
        initial_queries = len(connection.queries) if settings.DEBUG else 0

        try:
            # Step 1: Pre-fetch all mapping components to avoid N+1 queries during iteration
            portfolio = (
                Portfolio.objects.filter(user=user).select_related("allocation_strategy").first()
            )

            # Index all user strategies with their targets prefetched
            user_strategies = {
                s.id: s
                for s in AllocationStrategy.objects.filter(user=user).prefetch_related(
                    "target_allocations__asset_class"
                )
            }

            # Add portfolio strategy to the index if it exists and not already there
            if (
                portfolio
                and portfolio.allocation_strategy_id
                and portfolio.allocation_strategy_id not in user_strategies
            ):
                # Rare case: portfolio strategy owned by another user (not expected in this app)
                # but we'll fetch it just in case to be safe
                s = portfolio.allocation_strategy
                # Manual prefetch if needed (or just let it query once)
                if s:
                    user_strategies[s.id] = s

            # Map account types to strategies
            at_assignments = {
                a.account_type_id: a.allocation_strategy_id
                for a in AccountTypeStrategyAssignment.objects.filter(user=user)
            }

            # Step 2: Fetch accounts with all other relationships
            from django.db.models import OuterRef, Prefetch, Subquery

            from portfolio.models import Holding, SecurityPrice

            # Subquery for latest price to avoid N+1 and duplicates
            latest_price = Subquery(
                SecurityPrice.objects.filter(security_id=OuterRef("security_id"))
                .order_by("-price_datetime")
                .values("price")[:1]
            )

            holdings_qs = Holding.objects.annotate(
                _annotated_latest_price=latest_price
            ).select_related("security__asset_class")

            accounts = list(
                Account.objects.filter(user=user)
                .select_related(
                    "account_type",
                    "account_type__group",
                    "institution",
                )
                .prefetch_related(
                    Prefetch("holdings", queryset=holdings_qs),
                )
                .order_by("account_type__group__sort_order", "name")
            )

            if not accounts:
                logger.info("no_accounts_for_sidebar", user_id=user.id)
                return {
                    "grand_total": Decimal("0.00"),
                    "account_totals": {},
                    "account_variances": {},
                    "accounts_by_group": OrderedDict(),
                    "query_count": 0,
                }

            # Step 3: Calculate all totals and variances in one pass using in-memory data
            account_totals: dict[int, Decimal] = {}
            account_variances: dict[int, float] = {}

            for acc in accounts:
                # 1. Calculate holding totals by asset class (IN MEMORY)
                holdings_by_ac: dict[str, Decimal] = {}
                acc_total = Decimal("0.00")
                for h in acc.holdings.all():
                    ac_name = h.security.asset_class.name
                    val = h.market_value
                    holdings_by_ac[ac_name] = holdings_by_ac.get(ac_name, Decimal("0.00")) + val
                    acc_total += val

                if acc_total > 0:
                    account_totals[acc.id] = acc_total

                # 2. Determine Effective Strategy (IN MEMORY Fallback logic)
                strategy_id = None
                if acc.allocation_strategy_id:
                    strategy_id = acc.allocation_strategy_id
                elif acc.account_type_id in at_assignments:
                    strategy_id = at_assignments[acc.account_type_id]
                elif portfolio:
                    strategy_id = portfolio.allocation_strategy_id

                # 3. Calculate variance (IN MEMORY)
                strategy = user_strategies.get(strategy_id) if strategy_id else None
                if strategy:
                    # get_allocations_by_name uses target_allocations.all() which is prefetched
                    targets = {
                        ta.asset_class.name: ta.target_percent
                        for ta in strategy.target_allocations.all()
                    }

                    total_deviation = Decimal("0.00")
                    all_asset_classes = set(targets.keys()) | set(holdings_by_ac.keys())
                    for ac_name in all_asset_classes:
                        actual = holdings_by_ac.get(ac_name, Decimal("0.00"))
                        target_pct = targets.get(ac_name, Decimal("0.00"))
                        target_value = acc_total * (target_pct / Decimal("100"))
                        total_deviation += abs(actual - target_value)

                    variance_pct = (
                        float(total_deviation / acc_total * 100) if acc_total > 0 else 0.0
                    )
                    account_variances[acc.id] = variance_pct
                else:
                    account_variances[acc.id] = 0.0

            grand_total = sum(account_totals.values(), Decimal("0.00"))

            # Step 4: Build groups structure
            all_groups = AccountGroup.objects.all().order_by("sort_order", "name")

            # Initialize groups structure
            groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
            for g in all_groups:
                groups[g.name] = {"label": g.name, "total": Decimal("0.00"), "accounts": []}

            # Add "Other" group for ungrouped accounts
            if "Other" not in groups:
                groups["Other"] = {"label": "Other", "total": Decimal("0.00"), "accounts": []}

            # Single iteration through accounts to build groups
            for acc in accounts:
                acc_total = account_totals.get(acc.id, Decimal("0.00"))
                acc_variance = account_variances.get(acc.id, 0.0)

                # Determine group (use prefetched data)
                group_name = (
                    acc.account_type.group.name
                    if acc.account_type and acc.account_type.group
                    else "Other"
                )

                if group_name not in groups:
                    groups[group_name] = {
                        "label": group_name,
                        "total": Decimal("0.00"),
                        "accounts": [],
                    }

                # Add account to group
                groups[group_name]["accounts"].append(
                    {
                        "id": acc.id,
                        "name": acc.name,
                        "total": acc_total,
                        "absolute_deviation_pct": acc_variance,
                        "institution": str(acc.institution) if acc.institution else "Direct",
                        "account_type": acc.account_type.label if acc.account_type else "Unknown",
                    }
                )

                # Accumulate group total
                groups[group_name]["total"] += acc_total

            # Remove empty groups
            groups = OrderedDict((k, v) for k, v in groups.items() if v["accounts"])

            # Calculate query count for monitoring (only in DEBUG)
            final_queries = len(connection.queries) if settings.DEBUG else 0
            query_count = final_queries - initial_queries if settings.DEBUG else 0

            logger.info(
                "sidebar_data_built",
                user_id=user.id,
                account_count=len(accounts),
                grand_total=float(grand_total),
                query_count=query_count,
            )

            return {
                "grand_total": grand_total,
                "account_totals": account_totals,
                "account_variances": account_variances,
                "accounts_by_group": groups,
                "query_count": query_count,
            }

        except Exception as e:
            logger.error(
                "sidebar_data_build_failed",
                user_id=user.id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            # Return empty structure on error
            return {
                "grand_total": Decimal("0.00"),
                "account_totals": {},
                "account_variances": {},
                "accounts_by_group": OrderedDict(),
                "query_count": 0,
            }

    def _get_asset_class_metadata_df(self, user: Any) -> pd.DataFrame:
        """Get asset class metadata as DataFrame (NEW)."""
        from portfolio.models import AssetClass

        qs = AssetClass.objects.select_related("category", "category__parent").values(
            "id",
            "name",
            "category__parent__code",
            "category__parent__label",
            "category__parent__sort_order",
            "category__code",
            "category__label",
            "category__sort_order",
        )

        df = pd.DataFrame(list(qs))

        if df.empty:
            return pd.DataFrame()

        df.columns = [
            "asset_class_id",
            "asset_class_name",
            "group_code",
            "group_label",
            "group_sort_order",
            "category_code",
            "category_label",
            "category_sort_order",
        ]

        df["is_cash"] = (df["category_code"] == "CASH") | (df["asset_class_name"] == "Cash")

        return df

    def _get_accounts_metadata_df(self, user: Any) -> pd.DataFrame:
        """Get account metadata as DataFrame (NEW)."""
        from portfolio.models import Account

        qs = (
            Account.objects.filter(user=user)
            .select_related("account_type")
            .values(
                "id",
                "name",
                "account_type__code",
                "account_type__label",
                "account_type__tax_treatment",
            )
        )

        df = pd.DataFrame(list(qs))

        if df.empty:
            return pd.DataFrame()

        df.columns = [
            "account_id",
            "account_name",
            "type_code",
            "type_label",
            "tax_treatment",
        ]

        return df

    def _get_targets_df(self, user: Any) -> pd.DataFrame:
        """Get all allocation targets as DataFrame (NEW)."""
        from portfolio.models import TargetAllocation

        qs = (
            TargetAllocation.objects.filter(strategy__user=user)
            .select_related("asset_class", "strategy")
            .values(
                "strategy__id",
                "strategy__name",
                "asset_class__id",
                "asset_class__name",
                "target_percent",
            )
        )

        df = pd.DataFrame(list(qs))

        if df.empty:
            return pd.DataFrame()

        df.columns = [
            "strategy_id",
            "strategy_name",
            "asset_class_id",
            "asset_class_name",
            "target_percent",
        ]

        return df

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

        # Calculate target value and variance (Vectorized)
        df["Target_Value"] = 0.0
        mask = df["Sec_Count"] > 0
        if mask.any():
            df.loc[mask, "Target_Value"] = df.loc[mask, "Account_Total"] * (
                df.loc[mask, "Target_Pct"] / df.loc[mask, "Sec_Count"] / 100.0
            )
        df["Value_Variance"] = df["Value"] - df["Target_Value"]

        # Rename Security to Ticker if needed
        if "Security" in df.columns:
            df.rename(columns={"Security": "Ticker"}, inplace=True)

        return df

    def build_holdings_dataframe(self, user: Any, account_id: int | None = None) -> pd.DataFrame:
        """
        Build holdings DataFrame with all necessary metadata for display.
        REFACTORED: Eliminates manual loops and n+1 queries using pandas merge.

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
        # 1. Get flat holdings (includes basic account/security info)
        df_holdings = self._get_holdings_df(user, account_id)
        if df_holdings.empty:
            return pd.DataFrame()

        # 2. Get asset metadata (hierarchy)
        df_meta = self._get_asset_class_metadata_df(user)

        # 3. Merge metadata onto holdings
        if not df_meta.empty:
            df = df_holdings.merge(
                df_meta, on="asset_class_id", how="left", suffixes=("_holdings", "")
            )
        else:
            df = df_holdings

        # 4. Handle Missing Metadata (Unclassified)
        fill_values = {
            "group_code": "UNC",
            "group_label": "Unclassified",
            "group_sort_order": 9999,
            "category_code": "UNC",
            "category_label": "Unclassified",
            "category_sort_order": 9999,
            "asset_class_name": "Unclassified",
            "account__account_type__group__name": "Uncategorized",
        }
        df = df.fillna(value=fill_values)

        # 5. Rename columns to match legacy API (CamelCase)
        # 5. Rename columns to match legacy API (CamelCase)
        rename_map = {
            "account_id": "Account_ID",
            "account_name": "Account_Name",
            "account_type_label": "Account_Type",
            "account__account_type__group__name": "Account_Category",
            "asset_class_name": "Asset_Class",
            "asset_class_id": "Asset_Class_ID",
            "category_label": "Asset_Category",
            "group_label": "Asset_Group",
            "group_code": "Group_Code",
            "group_sort_order": "Group_Sort_Order",
            "category_code": "Category_Code",
            "category_sort_order": "Category_Sort_Order",
            "ticker": "Ticker",
            "security_name": "Security_Name",
            "shares": "Shares",
            "price": "Price",
            "value": "Value",
        }

        df = df.rename(columns=rename_map)

        # Select and order columns to match exact expected output
        expected_cols = [
            "Account_ID",
            "Account_Name",
            "Account_Type",
            "Account_Category",
            "Asset_Class",
            "Asset_Class_ID",
            "Asset_Category",
            "Asset_Group",
            "Group_Code",
            "Group_Sort_Order",
            "Category_Code",
            "Category_Sort_Order",
            "Ticker",
            "Security_Name",
            "Shares",
            "Price",
            "Value",
        ]

        # Ensure all columns exist (in case of missing data)
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None

        return df[expected_cols]

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

        # Step 2.1: Add zero holdings for missing targets
        # If account_id is provided, only add zero holdings for that account.
        # Otherwise, this might get complicated for multiple accounts, but for now
        # we'll use the provided account_id (or 0 if None, though 0 isn't really used there).
        if account_id:
            df_zero = self._get_zero_holdings_for_missing_targets(
                df=df, targets_map=effective_targets_map, account_id=account_id
            )
            if not df_zero.empty:
                df = pd.concat([df, df_zero], ignore_index=True)

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
        # Calculate Share Targets and Variances (Vectorized)
        df_with_targets["Target_Shares"] = 0.0
        price_mask = df_with_targets["Price"] > 0
        if price_mask.any():
            df_with_targets.loc[price_mask, "Target_Shares"] = (
                df_with_targets.loc[price_mask, "Target_Value"]
                / df_with_targets.loc[price_mask, "Price"]
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

        logger.info("building_presentation_dataframe", user_id=user.id)

        # Step 1: Get holdings using optimized method
        df_flat = self.build_holdings_dataframe(user)
        if df_flat.empty:
            logger.info("empty_holdings_dataframe")
            return pd.DataFrame()

        logger.info("processing_presentation_data", user=user.username)

        # Pivot to create MultiIndex DataFrame expected by calculate_allocations
        df_pivot = df_flat.pivot_table(
            index=["Account_Type", "Account_Category", "Account_Name", "Account_ID"],
            columns=["Asset_Class", "Asset_Category", "Ticker"],
            values="Value",
            aggfunc="sum",
        ).fillna(0.0)

        # Pivot to create MultiIndex DataFrame expected by calculate_allocations
        df_pivot = df_flat.pivot_table(
            index=["Account_Type", "Account_Category", "Account_Name", "Account_ID"],
            columns=["Asset_Class", "Asset_Category", "Ticker"],
            values="Value",
            aggfunc="sum",
        ).fillna(0.0)

        allocations = self.calculate_allocations(df_pivot)

        # Step 2: Get metadata
        # Step 2: Get metadata
        df_ac_meta = self._get_asset_class_metadata_df(user)
        _account_list, accounts_by_type = self._get_account_metadata(user)
        target_strategies = self._get_target_strategies(user)

        # Step 3: Pre-calculate totals
        portfolio_total = float(allocations["by_asset_class"]["dollars"].sum())
        account_totals = self._calculate_account_totals(allocations, accounts_by_type)

        # Step 4: Build base DataFrame with all asset classes (NO LOOPS)
        df = self._build_asset_class_base_dataframe(df_ac_meta)

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
        df_meta: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build base DataFrame with all asset classes and metadata using vectorized DataFrame.

        Returns:
            DataFrame with metadata columns and row_type='asset'
        """
        if df_meta.empty:
            return pd.DataFrame()

        df = df_meta.copy()
        df["row_type"] = "asset"
        return df

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
    ) -> pd.DataFrame:
        """
        Calculate all aggregation levels and return single sorted DataFrame.
        REFACTORED: efficient concatenation and vectorized variance calculation.
        """
        if df.empty:
            return pd.DataFrame()

        # Get numeric columns (exclude metadata)
        numeric_cols = [
            col
            for col in df.columns
            if not col.startswith(("group_", "category_", "asset_class_", "row_", "is_"))
        ]

        # 1. Base Assets
        # Reset index to make group/category codes available as columns for concat
        df_assets = df.reset_index()
        df_assets["row_type"] = "asset"
        df_assets["sort_rank"] = 0

        # ... (Subtotal logic)
        category_counts = df.groupby(
            level=["group_code", "category_code"], sort=False, dropna=False
        ).size()
        non_redundant_categories = category_counts[category_counts > 1].index

        # Calc sums
        category_subtotals = (
            df[numeric_cols]
            .groupby(level=["group_code", "category_code"], sort=False, dropna=False)
            .sum()
        )
        # Filter
        category_subtotals = category_subtotals.loc[non_redundant_categories]

        if not category_subtotals.empty:
            metadata_cols = [
                "group_label",
                "category_label",
                "group_code",
                "category_code",
                "group_sort_order",
                "category_sort_order",
            ]
            existing_meta = [c for c in metadata_cols if c in df.columns]
            category_meta = (
                df[existing_meta]
                .groupby(level=["group_code", "category_code"], sort=False, dropna=False)
                .first()
            )
            category_subtotals = category_subtotals.join(category_meta)
            category_subtotals["row_type"] = "subtotal"
            category_subtotals["sort_rank"] = 1
            label = category_subtotals["category_label"].fillna("")
            category_subtotals["asset_class_name"] = label + " Total"
            # Reset index to align columns
            category_subtotals = category_subtotals.reset_index()

        # ... (Group Total logic)
        group_counts = df.groupby(level="group_code", sort=False, dropna=False).size()
        non_redundant_groups = group_counts[group_counts > 1].index

        group_totals = df[numeric_cols].groupby(level="group_code", sort=False, dropna=False).sum()
        group_totals = group_totals.loc[non_redundant_groups]

        if not group_totals.empty:
            metadata_cols = ["group_label", "group_code", "group_sort_order"]
            existing_meta = [c for c in metadata_cols if c in df.columns]
            group_meta = (
                df[existing_meta].groupby(level="group_code", sort=False, dropna=False).first()
            )
            group_totals = group_totals.join(group_meta)
            group_totals["row_type"] = "group_total"
            group_totals["sort_rank"] = 2
            label = group_totals["group_label"].fillna("")
            group_totals["asset_class_name"] = label + " Total"
            # Fill category info max for sorting
            group_totals["category_sort_order"] = 99999
            group_totals["category_code"] = "ZZZ"
            group_totals["category_label"] = "Total"
            group_totals = group_totals.reset_index()

        # ... (Grand Total)
        grand_total = df[numeric_cols].sum().to_frame().T
        grand_total["row_type"] = "grand_total"
        grand_total["sort_rank"] = 3
        grand_total["asset_class_name"] = "Total"
        grand_total["group_sort_order"] = 99999
        grand_total["group_code"] = "ZZZ"
        grand_total["group_label"] = "Total"
        grand_total["category_sort_order"] = 99999
        grand_total["category_code"] = "ZZZ"
        grand_total["category_label"] = ""
        # grand_total has no MultiIndex, it's flat

        # Concat
        dfs_to_concat = [df_assets]
        if not category_subtotals.empty:
            dfs_to_concat.append(category_subtotals)
        if not group_totals.empty:
            dfs_to_concat.append(group_totals)
        dfs_to_concat.append(grand_total)

        combined_df = pd.concat(dfs_to_concat, ignore_index=True)

        # Calculate Variance columns on the combined DataFrame
        df_data = combined_df  # alias

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
        # Identify prefixes from columns
        prefixes = set()
        for col in df_data.columns:
            if col.endswith("_actual"):
                prefixes.add(col[:-7])

        for prefix in prefixes:
            # Effective Variance (for Accounts and Account Types)
            effective_col = f"{prefix}_effective"
            if effective_col in df_data.columns:
                df_data[f"{prefix}_variance"] = df_data[f"{prefix}_actual"] - df_data[effective_col]
                # Percentage variance
                actual_pct_col = f"{prefix}_actual_pct"
                effective_pct_col = f"{prefix}_effective_pct"
                if actual_pct_col in df_data.columns and effective_pct_col in df_data.columns:
                    df_data[f"{prefix}_variance_pct"] = (
                        df_data[actual_pct_col] - df_data[effective_pct_col]
                    )

            # Policy Variance
            policy_col = f"{prefix}_policy"
            if policy_col in df_data.columns:
                df_data[f"{prefix}_policy_variance"] = (
                    df_data[f"{prefix}_actual"] - df_data[policy_col]
                )
                actual_pct_col = f"{prefix}_actual_pct"
                policy_pct_col = f"{prefix}_policy_pct"
                if actual_pct_col in df_data.columns and policy_pct_col in df_data.columns:
                    df_data[f"{prefix}_policy_variance_pct"] = (
                        df_data[actual_pct_col] - df_data[policy_pct_col]
                    )

        # Final Sort
        combined_df = combined_df.sort_values(
            by=[
                "group_sort_order",
                "group_code",
                "category_sort_order",
                "category_code",
                "sort_rank",
                "asset_class_name",
            ],
            ascending=[True, True, True, True, True, True],
        )

        return combined_df

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

        # 2. Fetch all target allocations for these strategies using DataFrame (Optimized)
        df_targets = self._get_targets_df(user)

        # Build map: strategy_id -> {ac_id: target_pct}
        strategy_targets: dict[int, dict[int, Decimal]] = defaultdict(dict)

        if not df_targets.empty:
            # Filter for relevant strategies
            # Ensure strategy_id matching types (int)
            mask = df_targets["strategy_id"].isin(strategy_ids)
            filtered_targets = df_targets[mask]

            for _, row in filtered_targets.iterrows():
                # Extract values (converting to Decimal if needed, though likely already Decimal from ORM)
                sid = row["strategy_id"]
                acid = row["asset_class_id"]
                # Handle potential float conversion by pandas
                val = row["target_percent"]
                if not isinstance(val, Decimal):
                    val = Decimal(str(val))
                strategy_targets[sid][acid] = val

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

        OPTIMIZED: When called after accounts are prefetched with:
            - holdings__security__asset_class
            - allocation_strategy__target_allocations__asset_class
        This method uses in-memory data with no additional queries.

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

    def _get_holdings_df(self, user: Any, account_id: int | None = None) -> pd.DataFrame:
        """Get holdings as DataFrame - NO PYTHON LOOPS (NEW)."""
        from django.db.models import OuterRef, Subquery

        from portfolio.models import Holding, SecurityPrice

        qs = Holding.objects.filter(account__user=user)

        if account_id:
            qs = qs.filter(account_id=account_id)

        # Subquery for latest price to avoid N+1 and duplicates
        latest_price = Subquery(
            SecurityPrice.objects.filter(security_id=OuterRef("security_id")).values("price")[:1]
        )

        qs = (
            qs.annotate(latest_price=latest_price)
            .select_related(
                "account",
                "account__account_type",
                "security",
                "security__asset_class",
            )
            .values(
                "account_id",
                "account__name",
                "account__account_type__code",
                "account__account_type__label",
                "account__account_type__group__name",
                "security__ticker",
                "security__name",
                "security__asset_class_id",
                "security__asset_class__name",
                "shares",
                "latest_price",
            )
        )

        # Use iterator for memory efficiency if needed, but list is fine for reasonable size
        data = list(qs)
        df = pd.DataFrame(data)

        if df.empty:
            return pd.DataFrame()

        df.columns = [
            "account_id",
            "account_name",
            "account_type_code",
            "account_type_label",
            "account__account_type__group__name",
            "ticker",
            "security_name",
            "asset_class_id",
            "asset_class_name",
            "shares",
            "price",
        ]

        # Handle null prices and calculate value
        df["price"] = df["price"].fillna(0.0).astype(float)
        df["shares"] = df["shares"].astype(float)
        df["value"] = df["shares"] * df["price"]

        return df

    def get_account_totals(self, user: Any) -> dict[int, Decimal]:
        """
        Get current total value for all user accounts.

        OPTIMIZED: This method now works efficiently with prefetched holdings.
        When called after accounts are prefetched with holdings, it uses the
        in-memory data instead of querying again.

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
        df = self._get_holdings_df(user)

        if df.empty:
            return {}

        # Pandas vectorized aggregation - much faster than Python loops
        account_totals = df.groupby("account_id")["value"].sum()

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

        # Step 2: Aggregate at all levels and sort (includes variance calculations)
        # Returns single sorted DataFrame
        aggregated_df = self.aggregate_presentation_levels(df)

        # Step 3: Format for display
        _, accounts_by_type = self._get_account_metadata(user)
        strategies = self._get_target_strategies(user)

        return self._format_presentation_rows(
            df=aggregated_df,
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

    def _get_zero_holdings_for_missing_targets(
        self, df: pd.DataFrame, targets_map: dict[int, dict[str, Decimal]], account_id: int = 0
    ) -> pd.DataFrame:
        """
        Create zero-holding rows for asset classes with targets but no holdings.

        Args:
            df: Existing holdings DataFrame
            targets_map: Dict of {account_id: {asset_class_name: target_pct}}
            account_id: Account ID (0 for portfolio-wide)

        Returns:
            DataFrame with zero-holding rows for missing asset classes
        """
        from portfolio.models import AssetClass, SecurityPrice

        account_targets = targets_map.get(account_id, {})
        if not account_targets:
            return pd.DataFrame()

        # Find missing asset classes
        existing_asset_classes = set()
        if not df.empty and "Asset_Class" in df.columns:
            existing_asset_classes = set(df["Asset_Class"].unique())

        missing_asset_classes = set(account_targets.keys()) - existing_asset_classes

        if not missing_asset_classes:
            return pd.DataFrame()

        # Build zero holdings using primary securities
        zero_holdings = []

        for ac_name in missing_asset_classes:
            try:
                asset_class = AssetClass.objects.select_related(
                    "primary_security", "category", "category__parent"
                ).get(name=ac_name)

                security = asset_class.primary_security

                if not security:
                    logger.warning(
                        "no_primary_security_for_asset_class",
                        asset_class=ac_name,
                        account_id=account_id,
                    )
                    continue

                # Get latest price for the primary security
                latest_price = SecurityPrice.get_latest_price(security)
                price = float(latest_price) if latest_price else 0.0

                zero_holding = {
                    "Account_ID": account_id,
                    "Account_Name": "Portfolio" if account_id == 0 else "",
                    "Ticker": security.ticker,
                    "Security_Name": security.name,
                    "Asset_Class": ac_name,
                    "Asset_Class_ID": asset_class.id,
                    "Asset_Category": asset_class.category.label,
                    "Asset_Group": (
                        asset_class.category.parent.label
                        if asset_class.category.parent
                        else asset_class.category.label
                    ),
                    "Group_Code": (
                        asset_class.category.parent.code
                        if asset_class.category.parent
                        else asset_class.category.code
                    ),
                    "Group_Sort_Order": (
                        asset_class.category.parent.sort_order
                        if asset_class.category.parent
                        else asset_class.category.sort_order
                    ),
                    "Category_Code": asset_class.category.code,
                    "Category_Sort_Order": asset_class.category.sort_order,
                    "Shares": 0.0,
                    "Price": price,
                    "Value": 0.0,
                }

                zero_holdings.append(zero_holding)

            except AssetClass.DoesNotExist:
                logger.warning("asset_class_not_found", name=ac_name)
                continue

        if not zero_holdings:
            return pd.DataFrame()

        logger.info(
            "created_zero_holdings",
            count=len(zero_holdings),
            asset_classes=[h["Asset_Class"] for h in zero_holdings],
            account_id=account_id,
        )

        return pd.DataFrame(zero_holdings)

    def get_aggregated_holdings_rows(
        self, user: Any, target_mode: str = "effective"
    ) -> list[dict[str, Any]]:
        """
        Calculate and format aggregated holdings across all accounts.

        Args:
            user: User object
            target_mode: Either "effective" or "policy"

        Returns:
            List of dicts with same structure as get_holdings_rows but aggregated by ticker
        """
        logger.info(
            "building_aggregated_holdings_rows",
            user_id=user.id,
            target_mode=target_mode,
        )

        # Step 1: Build holdings DataFrame for ALL accounts (account_id=None)
        df = self.build_holdings_dataframe(user, account_id=None)

        if df.empty:
            logger.info("no_holdings_for_aggregation", user_id=user.id)
            return []

        # Step 2: Aggregate by ticker (sum shares and values across accounts)
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

        df_aggregated = df.groupby("Ticker", as_index=False).agg(agg_dict)

        # Step 3: Create a synthetic "portfolio account" for target calculation
        # Use Account_ID = 0 to represent the aggregated portfolio
        df_aggregated["Account_ID"] = 0
        df_aggregated["Account_Name"] = "Portfolio"

        # Step 4: Get targets based on mode
        if target_mode == "policy":
            # Use portfolio-level policy strategy
            targets_map = self._get_portfolio_policy_targets(user)
        else:
            # Use weighted effective targets (aggregate of account-level targets)
            targets_map = self._get_portfolio_effective_targets(user)

        # Step 5: Add zero holdings for missing targets
        df_zero = self._get_zero_holdings_for_missing_targets(
            df=df_aggregated, targets_map=targets_map, account_id=0
        )

        if not df_zero.empty:
            df_final = pd.concat([df_aggregated, df_zero], ignore_index=True)
        else:
            df_final = df_aggregated

        # Step 6: Calculate detail (targets, variance) for everything
        df_with_targets = self.calculate_holdings_detail(df_final, targets_map)

        # Step 7: Calculate allocation percentages (already exists in calculate_holdings_with_targets)
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

        # Step 8: Calculate share targets (already exists in calculate_holdings_with_targets)
        df_with_targets["Target_Shares"] = 0.0
        price_mask = df_with_targets["Price"] > 0
        if price_mask.any():
            df_with_targets.loc[price_mask, "Target_Shares"] = (
                df_with_targets.loc[price_mask, "Target_Value"]
                / df_with_targets.loc[price_mask, "Price"]
            )
        df_with_targets["Shares_Variance"] = (
            df_with_targets["Shares"] - df_with_targets["Target_Shares"]
        )

        # Step 9: Sort and format (reuse existing formatter)
        df_with_targets = df_with_targets.sort_values(
            by=["Group_Sort_Order", "Category_Sort_Order", "Target_Value", "Ticker"],
            ascending=[True, True, False, True],
        )

        return self._format_holdings_rows(df_with_targets)

    def _get_portfolio_effective_targets(self, user: Any) -> dict[int, dict[str, Decimal]]:
        """
        Get weighted-average effective targets for portfolio as a whole.

        Returns targets in format: {0: {asset_class_name: target_pct}}
        where 0 is the synthetic portfolio account ID.
        """
        # Get effective targets for each account
        effective_targets_map = self.get_effective_target_map(user)

        # Get account totals for weighting
        account_totals = self.get_account_totals(user)
        portfolio_total = sum(account_totals.values(), Decimal("0.00"))

        if portfolio_total == 0:
            return {0: {}}

        # Calculate weighted average
        portfolio_targets = {}

        for account_id, targets in effective_targets_map.items():
            account_value = account_totals.get(account_id, Decimal("0.00"))
            weight = float(account_value / portfolio_total)

            for asset_class, target_pct in targets.items():
                if asset_class not in portfolio_targets:
                    portfolio_targets[asset_class] = Decimal("0.00")
                portfolio_targets[asset_class] += Decimal(str(float(target_pct) * weight))

        return {0: portfolio_targets}

    def _get_portfolio_policy_targets(self, user: Any) -> dict[int, dict[str, Decimal]]:
        """
        Get portfolio-level policy targets.

        Returns targets in format: {0: {asset_class_name: target_pct}}
        where 0 is the synthetic portfolio account ID.
        """
        from portfolio.models import Portfolio

        # Try to find a portfolio with a strategy first, fallback to first portfolio
        portfolio = (
            Portfolio.objects.filter(user=user)
            .exclude(allocation_strategy=None)
            .select_related("allocation_strategy")
            .first()
        )
        if not portfolio:
            portfolio = (
                Portfolio.objects.filter(user=user).select_related("allocation_strategy").first()
            )

        if not portfolio:
            return {0: {}}

        policy_strategy = portfolio.allocation_strategy

        if not policy_strategy:
            return {0: {}}

        # Use existing get_allocations_by_name() method from AllocationStrategy
        return {0: policy_strategy.get_allocations_by_name()}

    def _format_presentation_rows(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, Any],
    ) -> list[dict[str, Any]]:
        logger.info("formatting_presentation_rows")
        """
        Format sorted aggregation DataFrame into display-ready rows.
        """
        if df.empty:
            return []

        # Convert sorted DataFrame rows to dicts
        # Since df is already sorted by aggregate_presentation_levels,
        # we just need to format each row.
        return self._dataframe_rows_to_dicts(df, accounts_by_type, target_strategies)

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

        # Ensure boolean flags are not NaN (NaN evaluates to True in templates)
        if "is_cash" in df_reset.columns:
            df_reset["is_cash"] = df_reset["is_cash"].fillna(False).astype(bool)

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
        asset_class_name = row.get("asset_class_name")
        if pd.isna(asset_class_name) or not asset_class_name:
            if row_type == "grand_total":
                asset_class_name = "Total"
            elif row_type == "group_total":
                label = row.get("group_label")
                group_label = label if pd.notna(label) else ""
                asset_class_name = f"{group_label} Total"
            elif row_type == "subtotal":
                label = row.get("category_label")
                cat_label = label if pd.notna(label) else ""
                asset_class_name = f"{cat_label} Total"

        raw_acid = row.get("asset_class_id", 0)
        acid = int(raw_acid) if pd.notna(raw_acid) else 0

        result = {
            "row_type": row_type,
            "asset_class_id": acid,
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

            is_zero_holding = float(row["Shares"]) == 0.0 and float(row["Value"]) == 0.0

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
                    "account_name": row["Account_Name"],
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
                    "is_zero_holding": is_zero_holding,
                    "parent_id": parent_id,
                    "row_class": f"{parent_id}-rows collapse show"
                    + (" table-light text-muted fst-italic" if is_zero_holding else ""),
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

    def build_target_allocation_context(self, *, user: Any) -> dict[str, Any]:
        """
        Build context data for target allocation view.

        This is a pure calculation/data transformation method that:
        1. Gets presentation rows via get_presentation_rows()
        2. Extracts portfolio total from the grand total row
        3. Fetches user's allocation strategies

        Returns dict with:
        - allocation_rows_percent: Presentation rows for percent display
        - allocation_rows_money: Presentation rows for dollar display
        - strategies: QuerySet of user's allocation strategies
        - portfolio_total_value: Total portfolio value as Decimal

        Args:
            user: The user whose allocations to display

        Returns:
            Dictionary containing view context data
        """
        from portfolio.models import AllocationStrategy

        logger.info("building_target_allocation_context", user_id=cast(Any, user).id)

        # Get presentation rows using existing engine method
        allocation_rows = self.get_presentation_rows(user=user)

        # Extract portfolio total from grand total row
        portfolio_total = Decimal("0.00")
        if allocation_rows:
            grand_total_row = next((r for r in allocation_rows if r.get("is_grand_total")), None)
            if grand_total_row and "portfolio" in grand_total_row:
                portfolio_total = Decimal(str(grand_total_row["portfolio"]["actual"]))

        # Get user's strategies
        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        return {
            "allocation_rows_percent": allocation_rows,
            "allocation_rows_money": allocation_rows,  # Same rows, template handles formatting
            "strategies": strategies,
            "portfolio_total_value": portfolio_total,
        }

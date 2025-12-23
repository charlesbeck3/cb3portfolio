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
        df["Variance"] = df["Value"] - df["Target_Value"]

        # Rename Security to Ticker if needed
        if "Security" in df.columns:
            df.rename(columns={"Security": "Ticker"}, inplace=True)

        return df

    def build_presentation_dataframe(
        self,
        user: Any,
    ) -> pd.DataFrame:
        """
        Build hierarchical presentation DataFrame with MultiIndex.

        This is the MAIN NEW METHOD that replaces the old presentation logic.

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

        # Calculate current allocations
        allocations = self.calculate_allocations(holdings_df)

        # Get metadata
        ac_metadata, hierarchy = self._get_asset_class_metadata(user)
        account_list, accounts_by_type = self._get_account_metadata(user)
        target_strategies = self._get_target_strategies(user)

        # Pre-calculate totals
        portfolio_total = float(allocations["by_asset_class"]["dollars"].sum())
        account_totals = self._calculate_account_totals(allocations, accounts_by_type)

        # Build asset-level data
        asset_rows = []

        for group_code in sorted(hierarchy.keys()):
            group_categories = hierarchy[group_code]

            for category_code in sorted(group_categories.keys()):
                asset_classes = group_categories[category_code]

                for ac_name in asset_classes:
                    ac_meta = ac_metadata[ac_name]
                    ac_id = ac_meta["id"]

                    row = self._build_asset_row_data(
                        ac_id=ac_id,
                        ac_name=ac_name,
                        ac_meta=ac_meta,
                        allocations=allocations,
                        accounts_by_type=accounts_by_type,
                        target_strategies=target_strategies,
                        portfolio_total=portfolio_total,
                        account_totals=account_totals,
                    )

                    asset_rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(asset_rows)

        # Set MultiIndex
        df = df.set_index(["group_code", "category_code", "asset_class_name"])

        return df

    def aggregate_presentation_levels(
        self,
        df: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        """
        Calculate all aggregation levels using pandas groupby.

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
        category_counts = df.groupby(level=["group_code", "category_code"]).size()
        category_subtotals = df[numeric_cols].groupby(level=["group_code", "category_code"]).sum()

        # Filter redundant categories (only 1 asset)
        non_redundant_categories = category_counts[category_counts > 1].index
        category_subtotals = category_subtotals.loc[non_redundant_categories]

        # Add metadata for category rows
        for idx in category_subtotals.index:
            group_code, category_code = idx
            # Get labels from first asset in this category
            first_asset = df.loc[idx]
            if isinstance(first_asset, pd.DataFrame):
                first_asset = first_asset.iloc[0]

            category_subtotals.loc[idx, "group_label"] = first_asset["group_label"]
            category_subtotals.loc[idx, "category_label"] = first_asset["category_label"]
            category_subtotals.loc[idx, "group_code"] = group_code
            category_subtotals.loc[idx, "category_code"] = category_code
            category_subtotals.loc[idx, "row_type"] = "subtotal"

        # Group totals: group by first index level only
        group_counts = df.groupby(level="group_code").size()
        group_totals = df[numeric_cols].groupby(level="group_code").sum()

        # Filter redundant groups (only 1 asset child)
        non_redundant_groups = group_counts[group_counts > 1].index
        group_totals = group_totals.loc[non_redundant_groups]

        # Add metadata for group rows
        for group_code in group_totals.index:
            # Get label from first asset in this group
            first_asset = df.loc[group_code]
            if isinstance(first_asset, pd.DataFrame):
                first_asset = first_asset.iloc[0]

            group_totals.loc[group_code, "group_label"] = first_asset["group_label"]
            group_totals.loc[group_code, "group_code"] = group_code
            group_totals.loc[group_code, "row_type"] = "group_total"

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

    def _build_asset_row_data(
        self,
        ac_id: int,
        ac_name: str,
        ac_meta: dict[str, Any],
        allocations: dict[str, pd.DataFrame],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, dict[int, dict[int, Decimal]]],
        portfolio_total: float,
        account_totals: dict[str, dict[int, float]],
    ) -> dict[str, Any]:
        """
        Build a single asset class row with all NUMERIC calculations.

        Returns dict with raw numeric values - NO formatting.
        """
        df_portfolio = allocations["by_asset_class"]
        df_account_type = allocations["by_account_type"]
        df_account = allocations["by_account"]

        # Metadata
        row = {
            "group_code": ac_meta["group_code"],
            "group_label": ac_meta["group_label"],
            "category_code": ac_meta["category_code"],
            "category_label": ac_meta["category_label"],
            "asset_class_name": ac_name,
            "asset_class_id": ac_id,
            "row_type": "asset",
            "is_cash": ac_meta["category_code"] == "CASH" or ac_name == "Cash",
        }

        # Portfolio-level current
        portfolio_current = 0.0
        if not df_portfolio.empty and ac_name in df_portfolio.index:
            portfolio_current = float(df_portfolio.loc[ac_name, "dollars"])

        row["portfolio_current"] = portfolio_current

        # Calculate portfolio target (weighted sum from accounts)
        portfolio_target = 0.0

        # Iterate through account types to calculate columns
        for type_id, type_accounts in sorted(accounts_by_type.items()):
            type_label = type_accounts[0]["type_label"] if type_accounts else ""
            type_code = type_accounts[0]["type_code"] if type_accounts else ""

            # Account type current
            at_current = 0.0
            col_name = f"{ac_name}_dollars"
            if (
                not df_account_type.empty
                and type_label in df_account_type.index
                and col_name in df_account_type.columns
            ):
                at_current = float(df_account_type.loc[type_label, col_name])

            row[f"{type_code}_current"] = at_current

            # Account type target input (from strategy assignment)
            at_target_input = None
            if type_id in target_strategies.get("account_type", {}):
                type_targets = target_strategies["account_type"][type_id]
                at_target_input = float(type_targets.get(ac_id, 0.0))

            row[f"{type_code}_target_input"] = at_target_input if at_target_input is not None else 0.0

            # Account type weighted target (sum of account targets)
            at_weighted_target = 0.0

            # Process individual accounts
            for acc_meta in type_accounts:
                acc_id = acc_meta["id"]
                acc_name_str = acc_meta["name"]

                # Account current
                acc_current = 0.0
                acc_total = account_totals["account"].get(acc_id, 0.0)

                if (
                    not df_account.empty
                    and acc_id in df_account.index
                    and col_name in df_account.columns
                ):
                    acc_current = float(df_account.loc[acc_id, col_name])

                # Account target
                acc_target_pct = 0.0
                if acc_id in target_strategies.get("account", {}):
                    acc_targets = target_strategies["account"][acc_id]
                    acc_target_pct = float(acc_targets.get(ac_id, 0.0))
                elif at_target_input is not None:
                    acc_target_pct = at_target_input

                acc_target = acc_total * (acc_target_pct / 100.0)
                acc_variance = acc_current - acc_target

                # Store in row
                acc_prefix = f"{type_code}_{acc_name_str}"
                row[f"{acc_prefix}_current"] = acc_current
                row[f"{acc_prefix}_target"] = acc_target
                row[f"{acc_prefix}_variance"] = acc_variance
                row[f"{acc_prefix}_target_pct"] = acc_target_pct
                row[f"{acc_prefix}_current_pct"] = (
                    (acc_current / acc_total * 100) if acc_total > 0 else 0.0
                )

                # Accumulate for account type
                at_weighted_target += acc_target

            # Calculate account type weighted percentage
            at_total = account_totals["account_type"].get(type_id, 0.0)
            at_weighted_pct = (at_weighted_target / at_total * 100) if at_total > 0 else 0.0
            at_variance = at_current - at_weighted_target

            row[f"{type_code}_weighted_target"] = at_weighted_target
            row[f"{type_code}_weighted_target_pct"] = at_weighted_pct
            row[f"{type_code}_variance"] = at_variance
            row[f"{type_code}_current_pct"] = (at_current / at_total * 100) if at_total > 0 else 0.0

            # Accumulate for portfolio
            portfolio_target += at_weighted_target

        # Portfolio target and variance
        portfolio_target_pct = (portfolio_target / portfolio_total * 100) if portfolio_total > 0 else 0.0
        portfolio_current_pct = (portfolio_current / portfolio_total * 100) if portfolio_total > 0 else 0.0
        portfolio_variance = portfolio_current - portfolio_target
        portfolio_variance_pct = portfolio_current_pct - portfolio_target_pct

        row["portfolio_target"] = portfolio_target
        row["portfolio_target_pct"] = portfolio_target_pct
        row["portfolio_variance"] = portfolio_variance
        row["portfolio_variance_pct"] = portfolio_variance_pct
        row["portfolio_current_pct"] = portfolio_current_pct

        return row

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

        Used by HoldingsView and calculate_holdings_detail.
        """
        from portfolio.models import Account, AssetClass

        # Get target strategies
        strategies_data = self._get_target_strategies(user)
        account_targets = strategies_data["account"]
        type_targets = strategies_data["account_type"]

        # Asset class ID to name map
        ac_map = {ac.id: ac.name for ac in AssetClass.objects.all()}

        # Get accounts
        accounts = Account.objects.filter(user=user)

        result = {}

        for account in accounts:
            acc_id = account.id
            at_id = account.account_type_id

            # Determine effective strategy (Account > Account Type)
            effective_ac_ids = {}

            if acc_id in account_targets and account_targets[acc_id]:
                effective_ac_ids = account_targets[acc_id]
            elif at_id in type_targets:
                effective_ac_ids = type_targets[at_id]

            # Convert {ac_id: pct} to {ac_name: pct}
            name_map = {}
            for ac_id_key, pct in effective_ac_ids.items():
                if ac_id_key in ac_map:
                    name_map[ac_map[ac_id_key]] = pct

            result[acc_id] = name_map

        return result

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

        asset_classes = AssetClass.objects.select_related(
            "category", "category__parent"
        ).order_by("category__parent__sort_order", "category__sort_order", "name")

        ac_metadata = {}
        hierarchy: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        for ac in asset_classes:
            if ac.category.parent:
                group_code = ac.category.parent.code
                group_label = ac.category.parent.label
            else:
                group_code = ac.category.code
                group_label = ac.category.label

            cat_code = ac.category.code
            cat_label = ac.category.label

            ac_metadata[ac.name] = {
                "id": ac.id,
                "group_code": group_code,
                "group_label": group_label,
                "category_code": cat_code,
                "category_label": cat_label,
                "sort_order": ac.category.sort_order,
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

        accounts = Account.objects.filter(user=user).select_related("account_type").order_by(
            "account_type__group__sort_order", "account_type__label", "name"
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
            AssetClass,
            TargetAllocation,
        )

        result: dict[str, Any] = {
            "account_type": {},
            "account": {},
            "at_strategy_map": {},
            "acc_strategy_map": {},
        }

        # Account Type assignments
        at_assignments = AccountTypeStrategyAssignment.objects.filter(
            user=user
        ).select_related("allocation_strategy")

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

        # Implicit Cash Calculation
        cash_ac = AssetClass.objects.filter(name="Cash").first()
        cash_id = cash_ac.id if cash_ac else None

        if cash_id:
            for strat_id in strategy_ids:
                targets = strategy_targets[strat_id]
                total_allocated = sum(targets.values())
                remainder = Decimal("100.0") - total_allocated

                if remainder > Decimal("0.001"):
                    targets[cash_id] = targets.get(cash_id, Decimal("0.0")) + remainder

        # Map to account types
        for at_id, strategy_id in at_strategy_map.items():
            result["account_type"][at_id] = strategy_targets.get(strategy_id, {})

        # Map to accounts
        for acc_id, strategy_id in acc_strategy_map.items():
            result["account"][acc_id] = strategy_targets.get(strategy_id, {})

        result["at_strategy_map"] = at_strategy_map
        result["acc_strategy_map"] = acc_strategy_map

        return result

    def _empty_allocations(self) -> dict[str, pd.DataFrame]:
        """Return empty DataFrames for empty portfolio."""
        return {
            "by_account": pd.DataFrame(),
            "by_account_type": pd.DataFrame(),
            "by_asset_class": pd.DataFrame(),
            "portfolio_summary": pd.DataFrame(),
        }

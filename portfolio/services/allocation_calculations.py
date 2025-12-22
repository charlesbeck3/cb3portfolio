"""
Pure pandas-based allocation calculations using MultiIndex DataFrames.
Zero Django dependencies - can be tested with mock DataFrames.
"""

from decimal import Decimal
from typing import Any

import pandas as pd


class AllocationCalculationEngine:
    """
    Calculate portfolio allocations at all hierarchy levels.

    Uses pandas groupby operations on MultiIndex for clean aggregation.
    """

    def calculate_allocations(
        self,
        holdings_df: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        """
        Calculate allocations at all levels from portfolio holdings.

        Args:
            holdings_df: MultiIndex DataFrame from Portfolio.to_dataframe()
                Rows: (Account_Type, Account_Category, Account_Name)
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
            "by_account": self._calculate_by_account(holdings_df),
            "by_account_type": self._calculate_by_account_type(holdings_df),
            "by_asset_class": self._calculate_by_asset_class(holdings_df, total_value),
            "portfolio_summary": self._calculate_portfolio_summary(holdings_df, total_value),
        }

    def _calculate_by_account(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate allocation for each account.

        Returns:
            DataFrame with rows = accounts, columns = asset classes
            Shows both dollar amounts and percentages
        """
        # Dataframe index now includes Account_ID.
        # We want to group by Account_Name (and Type/Cat/ID to stay unique).
        # Simply grouping by columns (Asset Class) sums across securities.
        by_asset_class = df.groupby(
            level=["Account_Type", "Account_Category", "Account_Name"]
        ).sum()
        # But wait, groupby sum loses the specific levels if we don't include them?
        # Actually `sum(axis=1)` sums securities (columns).

        # Step 1: Sum across securities to get total per Asset Class per Row (Account)
        by_asset_class = df.T.groupby(level="Asset_Class").sum().T

        # Step 2: Set index to Account_ID for easier lookup
        # Reset index to get all index levels as columns, then set only Account_ID as index
        if "Account_ID" in by_asset_class.index.names:
            by_asset_class = by_asset_class.reset_index()
            # Drop non-numeric columns (Account_Type, Account_Category, Account_Name)
            # Keep only Account_ID and asset class columns
            non_numeric_cols = ["Account_Type", "Account_Category", "Account_Name"]
            by_asset_class = by_asset_class.drop(columns=[c for c in non_numeric_cols if c in by_asset_class.columns])
            by_asset_class = by_asset_class.set_index("Account_ID")

        # Calculate account totals (now only numeric columns)
        account_totals = by_asset_class.sum(axis=1)

        # Calculate percentages
        percentages = by_asset_class.div(account_totals, axis=0).fillna(0.0) * 100

        # Combine into single DataFrame with MultiIndex columns
        result = pd.concat(
            [by_asset_class.add_suffix("_dollars"), percentages.add_suffix("_pct")],
            axis=1,
        )

        # Sort values
        result = result.reindex(sorted(result.columns), axis=1)

        return result

    def _calculate_by_account_type(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate allocation for each account type.

        Aggregates across all accounts within each type.
        """
        # Sum all holdings within each account type
        # Index is (Account_Type, Account_Category, Account_Name, Account_ID)
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

    def calculate_holdings_detail(
        self, holdings_df: pd.DataFrame, effective_targets_map: dict[int, dict[str, Decimal]]
    ) -> pd.DataFrame:
        """
        Calculate detailed holdings view with targets and variance.

        Args:
            holdings_df: Long-format DataFrame.
                Required Cols: Account_ID, Asset_Class, Security (or Ticker), Value, Shares, Price
            effective_targets_map: {account_id: {asset_class_name: target_pct}}

        Returns:
            DataFrame with columns: [..., Target_Value, Variance, ...]
        """
        if holdings_df.empty:
            return pd.DataFrame()

        df = holdings_df.copy()

        # Ensure we have Value
        if "Value" not in df.columns:
            # Maybe calculate from Shares * Price if missing?
            # But caller should provide it.
            return pd.DataFrame()

        # 1. Calculate Account Totals for Target distribution
        # Group by Account_ID to ensure uniqueness
        # Ensure Account_ID is column (reset index if needed, but we expect column for long format)
        if "Account_ID" not in df.columns and "Account_ID" in df.index.names:
            df = df.reset_index()

        account_totals = df.groupby("Account_ID")["Value"].sum()

        # Determine the column name for security identifier
        security_col_name = "Ticker" if "Ticker" in df.columns else "Security"

        # 3. Calculate Count of Securities per Asset Class per Account (to distribute target equally)
        # Group by [Account_ID, Asset_Class]
        sec_counts = df.groupby(["Account_ID", "Asset_Class"])[security_col_name].count()

        # 4. Apply Targets
        def calculate_row_target(row: Any) -> pd.Series:
            acc_id = row["Account_ID"]
            ac_name = row["Asset_Class"]

            # Get Account Total
            acc_total = account_totals.get(acc_id, 0.0)

            # Get Target % for this Asset Class
            targets = effective_targets_map.get(acc_id, {})
            ac_target_pct = float(targets.get(ac_name, Decimal(0)))

            # Get Count of securities in this bucket
            count = sec_counts.get((acc_id, ac_name), 1)

            # Distribute target
            security_target_pct = ac_target_pct / count if count > 0 else 0.0

            target_val = acc_total * (security_target_pct / 100.0)
            variance = row["Value"] - target_val

            return pd.Series([target_val, variance], index=["Target_Value", "Variance"])

        # Apply calculation
        # This might be slow for huge portfolios, but fine for typical use.
        # Vectorized alternative would be better but requires careful merge/join logic.

        # Vectorized Approach:
        # Create a targets Frame
        # keys: (Account_ID, Asset_Class)
        # val: Target_Pct

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

        # Calculate
        df["Target_Value"] = df.apply(
            lambda r: (r["Account_Total"] * (r["Target_Pct"] / r["Sec_Count"] / 100.0))
            if r["Sec_Count"] > 0
            else 0.0,
            axis=1,
        )
        df["Variance"] = df["Value"] - df["Target_Value"]

        # Use Ticker as Code
        df.rename(columns={"Security": "Ticker"}, inplace=True)

        return df

    def _calculate_by_asset_class(
        self,
        df: pd.DataFrame,
        total_value: float,
    ) -> pd.DataFrame:
        """
        Calculate portfolio-wide allocation by asset class.

        Returns:
            DataFrame with one row per asset class showing:
            - Dollar amount
            - Percentage of portfolio
        """
        if total_value == 0:
            return pd.DataFrame(columns=["Dollar_Amount", "Percentage"])

        # Sum across all accounts and securities within each asset class
        by_asset_class = df.T.groupby(level="Asset_Class").sum().T

        # Total for each asset class
        totals = by_asset_class.sum(axis=0)

        # Percentages
        percentages = (totals / total_value) * 100

        # Combine into result DataFrame
        result = pd.DataFrame(
            {
                "Dollar_Amount": totals,
                "Percentage": percentages,
            }
        )

        return result.sort_values("Dollar_Amount", ascending=False)

    def _calculate_portfolio_summary(
        self,
        df: pd.DataFrame,
        total_value: float,
    ) -> pd.DataFrame:
        """
        Calculate overall portfolio summary.

        Returns:
            Single-row DataFrame with portfolio totals
        """
        return pd.DataFrame(
            {
                "Total_Value": [total_value],
                "Number_of_Accounts": [len(df.index)],
                "Number_of_Holdings": [(df > 0).sum().sum()],
            }
        )



    def _format_money(self, val: Decimal) -> str:
        """Format decimal as money string: $1,234 or ($1,234)."""
        # Convert to float for formatting logic if needed, or keep decimal
        is_negative = val < 0
        abs_val = abs(val)
        s = f"${abs_val:,.0f}"
        return f"({s})" if is_negative else s



    # ===== Target Allocation Presentation Methods =====

    def get_target_allocation_presentation(
        self,
        user: Any,
        mode: str = "percent",  # 'percent' or 'dollar'
    ) -> list[dict[str, Any]]:
        """
        Generate presentation-ready data for target allocation table.

        Args:
            user: User object
            mode: 'percent' or 'dollar' for display formatting

        Returns:
            List of row dicts ready for template rendering
        """
        from portfolio.models import Portfolio

        # Step 1: Get holdings DataFrame
        portfolio = Portfolio.objects.filter(user=user).first()
        if not portfolio:
            return []

        holdings_df = portfolio.to_dataframe()
        if holdings_df.empty:
            return []

        # Step 2: Calculate current allocations
        allocations = self.calculate_allocations(holdings_df)

        # Step 3: Get metadata
        ac_metadata, hierarchy = self._get_asset_class_metadata(user)
        account_list, accounts_by_type = self._get_account_metadata(user)
        target_strategies = self._get_target_strategies(user)

        # Step 4: Build rows
        rows = self._build_presentation_rows(
            allocations=allocations,
            ac_metadata=ac_metadata,
            hierarchy=hierarchy,
            account_list=account_list,
            accounts_by_type=accounts_by_type,
            target_strategies=target_strategies,
            mode=mode,
        )

        return rows

    def _get_asset_class_metadata(
        self,
        user: Any,  # CustomUser type
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, list[str]]]]:
        """
        Gather asset class hierarchy metadata.

        Returns:
            Tuple of (ac_metadata, hierarchy)
            - ac_metadata: {ac_name: {id, group_code, group_label, category_code, category_label, sort_order}}
            - hierarchy: {group_code: {category_code: [ac_names]}}
        """
        from collections import defaultdict

        from portfolio.models import AssetClass

        asset_classes = AssetClass.objects.select_related("category", "category__parent").order_by(
            "category__parent__sort_order", "category__sort_order", "name"
        )

        ac_metadata = {}
        hierarchy: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        for ac in asset_classes:
            # Group is parent category (or category itself if no parent)
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
            Tuple of (account_list, accounts_by_type)
            - account_list: [{id, name, type_id, type_label, type_code}, ...]
            - accounts_by_type: {type_id: [account_dicts]}
        """
        from collections import defaultdict

        from portfolio.models import Account, AccountType

        AccountType.objects.filter(accounts__user=user).distinct().order_by(
            "group__sort_order", "label"
        )

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
    ) -> dict[str, dict[int, dict[int, Decimal]]]:
        """
        Gather target allocation strategies.

        Returns:
            {
                'account_type': {type_id: {ac_id: target_pct}},
                'account': {account_id: {ac_id: target_pct}}
            }
        """
        from collections import defaultdict

        from portfolio.models import Account, AccountTypeStrategyAssignment, TargetAllocation

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
        accounts = Account.objects.filter(user=user, allocation_strategy__isnull=False).select_related(
            "allocation_strategy"
        )

        acc_strategy_map = {}
        for acc in accounts:
            if acc.allocation_strategy_id:
                acc_strategy_map[acc.id] = acc.allocation_strategy_id
                strategy_ids.add(acc.allocation_strategy_id)

        # Fetch all target allocations for these strategies
        target_allocations = TargetAllocation.objects.filter(strategy_id__in=strategy_ids).select_related(
            "asset_class"
        )

        # Build map: strategy_id -> {ac_id: target_pct}
        strategy_targets: dict[int, dict[int, Decimal]] = defaultdict(dict)
        for ta in target_allocations:
            strategy_targets[ta.strategy_id][ta.asset_class_id] = ta.target_percent

        # Map to account types
        for at_id, strategy_id in at_strategy_map.items():
            result["account_type"][at_id] = strategy_targets.get(strategy_id, {})

        # Map to accounts
        for acc_id, strategy_id in acc_strategy_map.items():
            result["account"][acc_id] = strategy_targets.get(strategy_id, {})

        result["at_strategy_map"] = at_strategy_map
        result["acc_strategy_map"] = acc_strategy_map

        return result

    def _build_presentation_rows(
        self,
        allocations: dict[str, pd.DataFrame],
        ac_metadata: dict[str, dict[str, Any]],
        hierarchy: dict[str, dict[str, list[str]]],
        account_list: list[dict[str, Any]],
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, dict[int, dict[int, Decimal]]],
        mode: str,
    ) -> list[dict[str, Any]]:
        """Build presentation rows with all calculations."""

        rows = []

        df_portfolio = allocations["by_asset_class"]
        df_account_type = allocations["by_account_type"]
        df_account = allocations["by_account"]

        portfolio_total = (
            float(df_portfolio["Dollar_Amount"].sum()) if not df_portfolio.empty else 0.0
        )

        # Pre-calculate account and type totals
        # This is needed so that targets can be calculated for asset classes even if there are no holdings
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

        for group_code in sorted(hierarchy.keys()):
            group_categories = hierarchy[group_code]

            for category_code in sorted(group_categories.keys()):
                asset_classes = group_categories[category_code]

                # Asset rows
                for ac_name in asset_classes:
                    ac_meta = ac_metadata[ac_name]
                    ac_id = ac_meta["id"]

                    row = self._build_asset_row(
                        ac_id=ac_id,
                        ac_name=ac_name,
                        ac_meta=ac_meta,
                        df_portfolio=df_portfolio,
                        df_account_type=df_account_type,
                        df_account=df_account,
                        accounts_by_type=accounts_by_type,
                        target_strategies=target_strategies,
                        portfolio_total=portfolio_total,
                        mode=mode,
                        account_totals=account_totals,
                        account_type_totals=account_type_totals,
                    )
                    rows.append(row)

                # Category subtotal (if multiple assets in category)
                if len(asset_classes) > 1:
                    subtotal_row = self._build_category_subtotal(
                        category_code=category_code,
                        asset_classes=asset_classes,
                        ac_metadata=ac_metadata,
                        rows=rows,  # Use previously built asset rows
                    )
                    rows.append(subtotal_row)

            # Group total (if multiple categories in group)
            if len(group_categories) > 1:
                group_row = self._build_group_total(
                    group_code=group_code,
                    rows=rows,  # Use all rows for this group
                )
                rows.append(group_row)



        # Grand total
        grand_total_row = self._build_grand_total_presentation(
            rows=rows,
            portfolio_total=portfolio_total,
            mode=mode,
        )
        rows.append(grand_total_row)

        return rows

    def _build_asset_row(
        self,
        ac_id: int,
        ac_name: str,
        ac_meta: dict[str, Any],
        df_portfolio: pd.DataFrame,
        df_account_type: pd.DataFrame,
        df_account: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        target_strategies: dict[str, dict[int, dict[int, Decimal]]],
        portfolio_total: float,
        mode: str,
        account_totals: dict[int, float],
        account_type_totals: dict[int, float],
    ) -> dict[str, Any]:
        """Build a single asset class row with all calculations."""

        # Portfolio-level current
        portfolio_current_dollars = 0.0
        portfolio_current_pct = 0.0

        if not df_portfolio.empty and ac_name in df_portfolio.index:
            portfolio_current_dollars = float(df_portfolio.loc[ac_name, "Dollar_Amount"])
            portfolio_current_pct = float(df_portfolio.loc[ac_name, "Percentage"])

        # Build account type columns
        account_type_columns: list[dict[str, Any]] = []

        # Get unique account types from accounts_by_type
        for type_id in sorted(accounts_by_type.keys()):
            type_accounts = accounts_by_type[type_id]
            type_label = type_accounts[0]["type_label"] if type_accounts else ""
            type_code = type_accounts[0]["type_code"] if type_accounts else ""

            # Account type current
            at_current_dollars = 0.0
            at_current_pct = 0.0

            # Use pre-calculated total
            at_total_dollars = account_type_totals.get(type_id, 0.0)

            col_name = f"{ac_name}_dollars"
            if (
                not df_account_type.empty
                and type_label in df_account_type.index
                and col_name in df_account_type.columns
            ):
                at_current_dollars = float(df_account_type.loc[type_label, col_name])
                at_current_pct = (
                    (at_current_dollars / at_total_dollars * 100) if at_total_dollars > 0 else 0.0
                )

            # Account type target input
            at_target_input_pct: float | None = None
            if type_id in target_strategies.get("account_type", {}):
                type_targets = target_strategies["account_type"][type_id]
                at_target_input_pct = float(type_targets.get(ac_id, 0.0))

            # Account type weighted target (aggregated from accounts)
            at_weighted_target_dollars = 0.0
            at_weighted_target_pct = 0.0

            # Build individual account columns
            account_columns = []

            for acc_meta in type_accounts:
                acc_id = acc_meta["id"]
                acc_name = acc_meta["name"]

                # Account current
                acc_current_dollars = 0.0
                acc_current_pct = 0.0

                # Use pre-calculated total
                acc_total_dollars = account_totals.get(acc_id, 0.0)

                if (
                    not df_account.empty
                    and acc_id in df_account.index
                    and col_name in df_account.columns
                ):
                    acc_current_dollars = float(df_account.loc[acc_id, col_name])
                    acc_current_pct = (
                        (acc_current_dollars / acc_total_dollars * 100)
                        if acc_total_dollars > 0
                        else 0.0
                    )

                # Account target
                # Check for account-level override first, then fall back to account type
                acc_target_pct = 0.0
                if acc_id in target_strategies.get("account", {}):
                    acc_targets = target_strategies["account"][acc_id]
                    acc_target_pct = float(acc_targets.get(ac_id, 0.0))
                elif at_target_input_pct is not None:
                    acc_target_pct = at_target_input_pct

                acc_target_dollars = acc_total_dollars * (acc_target_pct / 100.0)
                acc_variance_dollars = acc_current_dollars - acc_target_dollars
                acc_variance_pct = acc_current_pct - acc_target_pct

                # Aggregate to account type weighted target
                at_weighted_target_dollars += acc_target_dollars

                # Format for display
                if mode == "percent":
                    acc_current_display = f"{acc_current_pct:.1f}%"
                    acc_target_display = f"{acc_target_pct:.1f}%"
                    acc_variance_display = f"{acc_variance_pct:+.1f}%"
                else:  # dollar
                    acc_current_display = f"${acc_current_dollars:,.0f}"
                    acc_target_display = f"${acc_target_dollars:,.0f}"
                    acc_variance_display = self._format_money(Decimal(str(acc_variance_dollars)))

                account_columns.append(
                    {
                        "id": acc_id,
                        "name": acc_name,
                        "current": acc_current_display,
                        "current_raw": acc_current_dollars,
                        "target": acc_target_display,
                        "target_raw": acc_target_dollars,
                        "target_pct": acc_target_pct,
                        "variance": acc_variance_display,
                        "variance_raw": acc_variance_dollars,
                        "allocation_strategy_id": target_strategies.get("acc_strategy_map", {}).get(acc_id),
                    }
                )

            # Calculate account type weighted target percentage
            at_weighted_target_pct = (
                (at_weighted_target_dollars / at_total_dollars * 100) if at_total_dollars > 0 else 0.0
            )
            at_variance_dollars = at_current_dollars - at_weighted_target_dollars
            at_variance_pct = at_current_pct - at_weighted_target_pct

            # Format for display
            if mode == "percent":
                at_current_display = f"{at_current_pct:.1f}%"
                at_weighted_display = f"{at_weighted_target_pct:.1f}%"
                at_variance_display = f"{at_variance_pct:+.1f}%"
            else:
                at_current_display = f"${at_current_dollars:,.0f}"
                at_weighted_display = f"${at_weighted_target_dollars:,.0f}"
                at_variance_display = self._format_money(Decimal(str(at_variance_dollars)))

            account_type_columns.append(
                {
                    "id": type_id,
                    "code": type_code,
                    "label": type_label,
                    "current": at_current_display,
                    "current_raw": at_current_dollars,
                    "target_input": at_target_input_pct if at_target_input_pct is not None else "",
                    "target_input_raw": at_target_input_pct if at_target_input_pct is not None else None,
                    "target_input_value": at_target_input_pct if at_target_input_pct is not None else "", # For compatibility
                    "weighted_target": at_weighted_display,
                    "weighted_target_raw": at_weighted_target_pct if mode == "percent" else at_weighted_target_dollars,
                    "variance": at_variance_display,
                    "variance_raw": at_variance_pct if mode == "percent" else at_variance_dollars,
                    "vtarget": at_variance_display, # For compatibility
                    "active_strategy_id": target_strategies.get("at_strategy_map", {}).get(type_id),
                    "active_accounts": account_columns,
                    "accounts": account_columns,
                }
            )

        # Portfolio target and variance
        # For now, we'll calculate portfolio target as sum of account type weighted targets
        portfolio_target_dollars = float(sum(atc["weighted_target_raw"] for atc in account_type_columns))
        portfolio_target_pct = (
            (portfolio_target_dollars / portfolio_total * 100) if portfolio_total > 0 else 0.0
        )
        portfolio_variance_dollars = portfolio_current_dollars - portfolio_target_dollars
        portfolio_variance_pct = portfolio_current_pct - portfolio_target_pct

        if mode == "percent":
            portfolio_current_display = f"{portfolio_current_pct:.1f}%"
            portfolio_target_display = f"{portfolio_target_pct:.1f}%"
            portfolio_variance_display = f"{portfolio_variance_pct:+.1f}%"
        else:
            portfolio_current_display = f"${portfolio_current_dollars:,.0f}"
            portfolio_target_display = f"${portfolio_target_dollars:,.0f}"
            portfolio_variance_display = self._format_money(Decimal(str(portfolio_variance_dollars)))

        return {
            "row_type": "asset",
            "asset_class_id": ac_id,
            "asset_class_name": ac_name,
            "group_code": ac_meta["group_code"],
            "group_label": ac_meta["group_label"],
            "category_code": ac_meta["category_code"],
            "category_label": ac_meta["category_label"],
            "is_asset": True,
            "is_subtotal": False,
            "is_group_total": False,
            "is_grand_total": False,
            "is_cash": ac_meta["category_code"] == "CASH" or ac_name == "Cash",
            "css_class": "",
            "portfolio": {
                "current": portfolio_current_display,
                "target": portfolio_target_display,
                "variance": portfolio_variance_display,
            },
            "account_types": account_type_columns,
        }

    def _build_category_subtotal(
        self,
        category_code: str,
        asset_classes: list[str],
        ac_metadata: dict[str, dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build category subtotal row by aggregating asset rows."""
        # Find all asset rows for this category
        category_rows = [
            r
            for r in rows
            if r.get("category_code") == category_code and r.get("is_asset") and not r.get("is_cash")
        ]

        if not category_rows:
            return {}

        # Get category label from first asset
        category_label = ac_metadata[asset_classes[0]]["category_label"]

        # Aggregate portfolio values
        portfolio_current = sum(
            float(r["portfolio"]["current"].replace("$", "").replace(",", "").replace("%", ""))
            for r in category_rows
        )
        portfolio_target = sum(
            float(r["portfolio"]["target"].replace("$", "").replace(",", "").replace("%", ""))
            for r in category_rows
        )
        portfolio_variance = portfolio_current - portfolio_target

        # Aggregate account type values
        account_type_columns = []
        if category_rows:
            # Get account types from first row
            for i, at in enumerate(category_rows[0]["account_types"]):
                at_current = sum(r["account_types"][i]["current_raw"] for r in category_rows)
                at_weighted = sum(r["account_types"][i]["weighted_target_raw"] for r in category_rows)
                at_variance = at_current - at_weighted

                # Aggregate accounts
                account_columns = []
                for j, acc in enumerate(at["accounts"]):
                    acc_current = sum(
                        r["account_types"][i]["accounts"][j]["current_raw"] for r in category_rows
                    )
                    acc_target = sum(
                        r["account_types"][i]["accounts"][j]["target_raw"] for r in category_rows
                    )
                    acc_variance = acc_current - acc_target

                    account_columns.append(
                        {
                            "id": acc["id"],
                            "name": acc["name"],
                            "current": f"${acc_current:,.0f}",
                            "current_raw": acc_current,
                            "target": f"${acc_target:,.0f}",
                            "target_raw": acc_target,
                            "variance": self._format_money(Decimal(str(acc_variance))),
                            "variance_raw": acc_variance,
                        }
                    )

                account_type_columns.append(
                    {
                        "id": at["id"],
                        "code": at.get("code"),
                        "label": at["label"],
                        "current": f"${at_current:,.0f}",
                        "current_raw": at_current,
                        "weighted_target": f"${at_weighted:,.0f}",
                        "weighted_target_raw": at_weighted,
                        "variance": self._format_money(Decimal(str(at_variance))),
                        "variance_raw": at_variance,
                        "vtarget": self._format_money(Decimal(str(at_variance))), # For compatibility
                        "active_accounts": account_columns,
                        "accounts": account_columns,
                    }
                )

        return {
            "row_type": "subtotal",
            "asset_class_id": 0,
            "asset_class_name": f"{category_label} Total",
            "group_code": ac_metadata[asset_classes[0]]["group_code"],
            "group_label": ac_metadata[asset_classes[0]]["group_label"],
            "category_code": category_code,
            "category_label": category_label,
            "is_asset": False,
            "is_subtotal": True,
            "is_group_total": False,
            "is_grand_total": False,
            "is_cash": False,
            "css_class": "subtotal",
            "portfolio": {
                "current": f"${portfolio_current:,.0f}",
                "target": f"${portfolio_target:,.0f}",
                "variance": self._format_money(Decimal(str(portfolio_variance))),
            },
            "account_types": account_type_columns,
        }

    def _build_group_total(
        self,
        group_code: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build group total row by aggregating category rows."""
        # Find all rows for this group (assets and subtotals, but not other group totals)
        group_rows = [
            r
            for r in rows
            if r.get("group_code") == group_code
            and not r.get("is_group_total")
            and not r.get("is_grand_total")
            and not r.get("is_cash")
        ]

        if not group_rows:
            return {}

        # Get group label from first row
        # We now have group_label in the asset rows
        group_label = next((r.get("group_label") for r in group_rows if r.get("group_label")), group_code)

        # Aggregate portfolio values
        portfolio_current = sum(
            float(r["portfolio"]["current"].replace("$", "").replace(",", "").replace("%", ""))
            for r in group_rows
            if not r.get("is_subtotal")  # Only count assets, not subtotals
        )
        portfolio_target = sum(
            float(r["portfolio"]["target"].replace("$", "").replace(",", "").replace("%", ""))
            for r in group_rows
            if not r.get("is_subtotal")
        )
        portfolio_variance = portfolio_current - portfolio_target

        # Similar aggregation for account types
        account_type_columns = []
        if group_rows:
            asset_rows = [r for r in group_rows if not r.get("is_subtotal")]
            if asset_rows:
                for i, at in enumerate(asset_rows[0]["account_types"]):
                    at_current = sum(r["account_types"][i]["current_raw"] for r in asset_rows)
                    at_weighted = sum(r["account_types"][i]["weighted_target_raw"] for r in asset_rows)
                    at_variance = at_current - at_weighted

                    account_columns = []
                    for j, acc in enumerate(at["accounts"]):
                        acc_current = sum(
                            r["account_types"][i]["accounts"][j]["current_raw"] for r in asset_rows
                        )
                        acc_target = sum(
                            r["account_types"][i]["accounts"][j]["target_raw"] for r in asset_rows
                        )
                        acc_variance = acc_current - acc_target

                        account_columns.append(
                            {
                                "id": acc["id"],
                                "name": acc["name"],
                                "current": f"${acc_current:,.0f}",
                                "current_raw": acc_current,
                                "target": f"${acc_target:,.0f}",
                                "target_raw": acc_target,
                                "variance": self._format_money(Decimal(str(acc_variance))),
                                "variance_raw": acc_variance,
                            }
                        )

                    account_type_columns.append(
                        {
                            "id": at["id"],
                            "code": at.get("code"),
                            "label": at["label"],
                            "current": f"${at_current:,.0f}",
                            "current_raw": at_current,
                            "weighted_target": f"${at_weighted:,.0f}",
                            "weighted_target_raw": at_weighted,
                            "variance": self._format_money(Decimal(str(at_variance))),
                            "variance_raw": at_variance,
                            "vtarget": self._format_money(Decimal(str(at_variance))), # For compatibility
                            "active_accounts": account_columns,
                            "accounts": account_columns,
                        }
                    )

        return {
            "row_type": "group_total",
            "asset_class_id": 0,
            "asset_class_name": f"{group_label} Total",
            "group_code": group_code,
            "group_label": group_label,
            "category_code": "",
            "is_asset": False,
            "is_subtotal": False,
            "is_group_total": True,
            "is_grand_total": False,
            "is_cash": False,
            "css_class": "group-total",
            "portfolio": {
                "current": f"${portfolio_current:,.0f}",
                "target": f"${portfolio_target:,.0f}",
                "variance": f"${portfolio_variance:+,.0f}",
            },
            "account_types": account_type_columns,
        }



    def _build_grand_total_presentation(
        self,
        rows: list[dict[str, Any]],
        portfolio_total: float,
        mode: str,
    ) -> dict[str, Any]:
        """Build grand total row by aggregating all asset rows."""
        # Filter to only asset rows (not subtotals, group totals, or cash)
        asset_rows = [
            r
            for r in rows
            if r.get("is_asset") and not r.get("is_subtotal") and not r.get("is_group_total")
        ]

        if not asset_rows:
            return {
                "row_type": "grand_total",
                "asset_class_id": 0,
                "asset_class_name": "Total",
                "group_code": "",
                "category_code": "",
                "is_asset": False,
                "is_subtotal": False,
                "is_group_total": False,
                "is_grand_total": True,
                "is_cash": False,
                "css_class": "grand-total",
                "portfolio": {
                    "current": "$0",
                    "target": "$0",
                    "variance": "$0",
                },
                "account_types": [],
            }

        # Aggregate portfolio values
        portfolio_current = sum(
            float(r["portfolio"]["current"].replace("$", "").replace(",", "").replace("%", ""))
            for r in asset_rows
        )
        portfolio_target = sum(
            float(r["portfolio"]["target"].replace("$", "").replace(",", "").replace("%", ""))
            for r in asset_rows
        )
        portfolio_variance = portfolio_current - portfolio_target

        # Aggregate account type values
        account_type_columns = []
        if asset_rows:
            for i, at in enumerate(asset_rows[0]["account_types"]):
                at_current = sum(r["account_types"][i]["current_raw"] for r in asset_rows)
                at_weighted = sum(r["account_types"][i]["weighted_target_raw"] for r in asset_rows)
                at_variance = at_current - at_weighted

                account_columns = []
                for j, acc in enumerate(at["accounts"]):
                    acc_current = sum(
                        r["account_types"][i]["accounts"][j]["current_raw"] for r in asset_rows
                    )
                    acc_target = sum(
                        r["account_types"][i]["accounts"][j]["target_raw"] for r in asset_rows
                    )
                    acc_variance = acc_current - acc_target

                    if mode == "percent":
                        acc_current_display = f"{acc_current:.1f}%"
                        acc_target_display = f"{acc_target:.1f}%"
                        acc_variance_display = f"{acc_variance:+.1f}%"
                    else:
                        acc_current_display = f"${acc_current:,.0f}"
                        acc_target_display = f"${acc_target:,.0f}"
                        acc_variance_display = f"${acc_variance:+,.0f}"

                    account_columns.append(
                        {
                            "id": acc["id"],
                            "name": acc["name"],
                            "current": acc_current_display,
                            "current_raw": acc_current,
                            "target": acc_target_display,
                            "target_raw": acc_target,
                            "variance": acc_variance_display if mode == "percent" else self._format_money(Decimal(str(acc_variance))),
                            "variance_raw": acc_variance,
                        }
                    )

                if mode == "percent":
                    at_current_display = f"{at_current:.1f}%"
                    at_weighted_display = f"{at_weighted:.1f}%"
                    at_variance_display = f"{at_variance:+.1f}%"
                else:
                    at_current_display = f"${at_current:,.0f}"
                    at_weighted_display = f"${at_weighted:,.0f}"
                    at_variance_display = f"${at_variance:+,.0f}"

                account_type_columns.append(
                    {
                        "id": at["id"],
                        "code": at.get("code"),
                        "label": at["label"],
                        "current": at_current_display,
                        "current_raw": at_current,
                        "weighted_target": at_weighted_display,
                        "weighted_target_raw": at_weighted,
                        "variance": at_variance_display if mode == "percent" else self._format_money(Decimal(str(at_variance))),
                        "variance_raw": at_variance,
                        "vtarget": at_variance_display if mode == "percent" else self._format_money(Decimal(str(at_variance))), # For compatibility
                        "active_accounts": account_columns,
                        "accounts": account_columns,
                    }
                )

        if mode == "percent":
            portfolio_current_display = f"{portfolio_current:.1f}%"
            portfolio_target_display = f"{portfolio_target:.1f}%"
            portfolio_variance_display = f"{portfolio_variance:+.1f}%"
        else:
            portfolio_current_display = f"${portfolio_current:,.0f}"
            portfolio_target_display = f"${portfolio_target:,.0f}"
            portfolio_variance_display = f"${portfolio_variance:+,.0f}"

        return {
            "row_type": "grand_total",
            "asset_class_id": 0,
            "asset_class_name": "Total",
            "group_code": "",
            "category_code": "",
            "is_asset": False,
            "is_subtotal": False,
            "is_group_total": False,
            "is_grand_total": True,
            "is_cash": False,
            "css_class": "grand-total",
            "portfolio": {
                "current": portfolio_current_display,
                "target": portfolio_target_display,
                "variance": portfolio_variance_display,
            },
            "account_types": account_type_columns,
        }

    def _empty_allocations(self) -> dict[str, pd.DataFrame]:
        """Return empty DataFrames for empty portfolio."""
        return {
            "by_account": pd.DataFrame(),
            "by_account_type": pd.DataFrame(),
            "by_asset_class": pd.DataFrame(),
            "portfolio_summary": pd.DataFrame(),
        }

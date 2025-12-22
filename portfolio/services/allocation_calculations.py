"""
Pure pandas-based allocation calculations using MultiIndex DataFrames.
Zero Django dependencies - can be tested with mock DataFrames.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import pandas as pd


@dataclass(frozen=True)
class AccountTypeColumnData:
    code: str
    label: str
    current: str
    target: str
    vtarget: str
    current_raw: Decimal
    target_raw: Decimal
    vtarget_raw: Decimal


@dataclass(frozen=True)
class AllocationTableRow:
    asset_class_id: int
    asset_class_name: str
    category_code: str
    is_subtotal: bool
    is_group_total: bool
    is_grand_total: bool
    is_cash: bool
    account_type_data: list[AccountTypeColumnData]
    portfolio_current: str
    portfolio_target: str
    portfolio_vtarget: str


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

        # Step 2: Ensure rows are unique Accounts.
        # The input DF has Account_ID in index.
        # We can keep it or drop it for this high-level view?
        # The legacy `by_account` view expected (Type, Cat, Name).
        # For compatibility with `TargetAllocationViewService` logic (which did reset_index),
        # let's try to maintain the shape but handle the extra level.
        # If we just keep the index as is, it has 4 levels.
        # TargetAllocationViewService.build_context explicitly handles MultiIndex and tries to reset.
        # Let's keep Account_ID in the index for uniqueness, it's safer.
        # But `_calculate_by_account_type` needs to handle it.

        # Calculate account totals
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

    def calculate_dashboard_rows(
        self,
        holdings_df: pd.DataFrame,
        account_types: list[Any],
        portfolio_total_value: Decimal,
        mode: str,
        cash_asset_class_id: int | None,
    ) -> list[AllocationTableRow]:
        """
        Builds allocation table rows for the dashboard using pandas aggregations.

        Replaces usage of AllocationTableBuilder.
        """
        rows: list[AllocationTableRow] = []
        effective_mode = "money" if mode == "dollar" else mode

        if holdings_df.empty:
            return self._build_empty_dashboard_rows(
                account_types, portfolio_total_value, effective_mode
            )

        # 1. Aggregate DataFrame to (Asset_Class, Asset_Category) x (Account_Type)
        # Groups: Asset_Class, Asset_Category -> sum
        # Columns: Account_Type -> sum
        # Result: DataFrame with Index=[Asset_Class, Asset_Category], Columns=[Account_Type]
        # values are market values

        # Flatten security dimension first
        # Sum across securities to get (Account_Type, Account_Category, Account_Name) x (Asset_Class, Asset_Category)
        df_by_ac = holdings_df.T.groupby(level=["Asset_Class", "Asset_Category"]).sum().T
        df_by_at_ac = df_by_ac.groupby(level="Account_Type").sum()  # Rows -> Account Type

        # Pivot so we have Asset Class as rows and Account Type as columns
        # df_grid: index=(Asset_Class, Asset_Category), columns=Account_Type
        df_grid = df_by_at_ac.T

        # We need Asset Class IDs and hierarchy.
        # Since the DataFrame only has names, we might need a lookup map if IDs are strictly required for links.
        # However, the original builder used `ac_data.id`.
        # For now, let's assume we can map names back to IDs if needed, or if IDs are not critical for pure display
        # (except for maybe links).
        # To be safe, we can fetch AssetClasses. But let's see if we can perform the calc without DB hits first.
        # The view passes `cash_asset_class_id`.

        # Let's organize hierarchy: Group -> Category -> Asset Class
        # The DF has Asset_Category. We need Asset_Group (which is category.parent).
        # We might need to look up metadata.
        # Optimization: Build a metadata map from the passed `target_allocations` or strict DB query if absolutely needed.
        # Or, we can rely on `AssetClass` objects linked to `account_types[].target_map` keys?
        # No, `target_map` keys are IDs.

        # Let's fetch AssetClass metadata to ensure we have IDs and Groups
        from portfolio.models import AssetClass

        ac_qs = AssetClass.objects.select_related("category__parent").all()
        ac_meta = {
            ac.name: {
                "id": ac.id,
                "category_code": ac.category.code,
                "category_label": ac.category.label,
                "group_code": ac.category.parent.code if ac.category.parent else ac.category.code,
                "group_label": ac.category.parent.label
                if ac.category.parent
                else ac.category.label,
            }
            for ac in ac_qs
        }

        # Now iterate through hierarchy
        # Structure: dict[Group, dict[Category, list[AssetClass]]]
        hierarchy: dict[str, dict[str, list[str]]] = {}

        # Helper to get AC name from index
        # index is MultiIndex(Asset_Class, Asset_Category)
        for ac_name, _ in df_grid.index:
            if ac_name not in ac_meta:
                # Fallback if somehow not in DB (e.g. test data mismatch)
                continue

            meta = ac_meta[ac_name]
            grp = str(meta["group_code"])
            cat = str(meta["category_code"])

            if grp not in hierarchy:
                hierarchy[grp] = {}
            if cat not in hierarchy[grp]:
                hierarchy[grp][cat] = []
            hierarchy[grp][cat].append(ac_name)

        # Build rows
        # Sort Groups? We need a sort order. Alphabetical or total value?
        # Original sort was by Total Value descending.

        # Calculate group totals for sorting
        group_totals = {}
        for grp, cats in hierarchy.items():
            val = 0.0
            for _cat, acs in cats.items():
                for ac in acs:
                    if (ac, ac_meta[ac]["category_label"]) in df_grid.index:
                        val += float(df_grid.loc[(ac, ac_meta[ac]["category_label"])].sum())
            group_totals[grp] = val

        sorted_groups = sorted(group_totals.keys(), key=lambda k: group_totals[k], reverse=True)

        for grp in sorted_groups:
            # Sort categories by total
            cat_totals = {}
            for cat, acs in hierarchy[grp].items():
                val = 0.0
                for ac in acs:
                    if (ac, ac_meta[ac]["category_label"]) in df_grid.index:
                        val += float(df_grid.loc[(ac, ac_meta[ac]["category_label"])].sum())
                cat_totals[cat] = val

            sorted_cats = sorted(cat_totals.keys(), key=lambda k: cat_totals[k], reverse=True)

            for cat in sorted_cats:
                # Sort asset classes by total
                acs = hierarchy[grp][cat]
                # Filter ACs that are CASH if we are hiding cash (handled later by manual row)
                # But here we filter generic rows

                ac_vals = {}
                for ac in acs:
                    meta = ac_meta[ac]
                    if (ac, meta["category_label"]) in df_grid.index:
                        ac_vals[ac] = float(df_grid.loc[(ac, meta["category_label"])].sum())

                sorted_acs = sorted(ac_vals.keys(), key=lambda k: ac_vals[k], reverse=True)

                for ac in sorted_acs:
                    # Build Asset Row
                    meta = ac_meta[ac]
                    idx = (ac, meta["category_label"])
                    row_values = df_grid.loc[idx] if idx in df_grid.index else pd.Series()
                    
                    # Determine if this is the cash row
                    is_cash_row = False
                    if cash_asset_class_id and meta["id"] == cash_asset_class_id:
                        is_cash_row = True

                    rows.append(
                        self._build_row(
                            label=ac,
                            ac_id=cast(int, meta["id"]),
                            cat_code=cat,
                            is_subtotal=False,
                            row_values=row_values,
                            account_types=account_types,
                            portfolio_total=portfolio_total_value,
                            mode=effective_mode,
                            # Pass map for targets logic
                            ac_targets={
                                at.code: at.target_map.get(meta["id"], Decimal(0))
                                for at in account_types
                            },
                            is_cash=is_cash_row,
                        )
                    )

                # Category Subtotal
                if len(sorted_acs) > 0 and len(hierarchy[grp][cat]) > 1:
                    # Calculate category total values
                    cat_acs = hierarchy[grp][cat]

                    cat_indices = [
                        (a, ac_meta[a]["category_label"])
                        for a in cat_acs
                        if (a, ac_meta[a]["category_label"]) in df_grid.index
                    ]

                    if cat_indices:
                        cat_values = df_grid.loc[cat_indices].sum(axis=0)
                        rows.append(
                            self._build_row(
                                label=f"{ac_meta[cat_acs[0]]['category_label']} Total",
                                ac_id=0,
                                cat_code=cat,
                                is_subtotal=True,
                                row_values=cat_values,
                                account_types=account_types,
                                portfolio_total=portfolio_total_value,
                                mode=effective_mode,
                                ac_targets=self._aggregate_targets(account_types, cat_acs, ac_meta),
                            )
                        )

            # Group Total
            if len(sorted_cats) > 1:
                # Calculate group values
                grp_acs = []
                for c in hierarchy[grp].values():
                    grp_acs.extend(c)

                grp_indices = [
                    (a, ac_meta[a]["category_label"])
                    for a in grp_acs
                    if (a, ac_meta[a]["category_label"]) in df_grid.index
                ]

                if grp_indices:
                    grp_values = df_grid.loc[grp_indices].sum(axis=0)
                    rows.append(
                        self._build_row(
                            label=f"{ac_meta[grp_acs[0]]['group_label']} Total",
                            ac_id=0,
                            cat_code="",
                            is_subtotal=False,
                            is_group_total=True,
                            row_values=grp_values,
                            account_types=account_types,
                            portfolio_total=portfolio_total_value,
                            mode=effective_mode,
                            ac_targets=self._aggregate_targets(account_types, grp_acs, ac_meta),
                        )
                    )

        # Grand Total
        # Sum entire grid
        grand_total_values = df_grid.sum(axis=0)
        rows.append(
            self._build_row(
                label="Total",
                ac_id=0,
                cat_code="",
                is_grand_total=True,
                row_values=grand_total_values,
                account_types=account_types,
                portfolio_total=portfolio_total_value,
                mode=effective_mode,
                # All targets
                ac_targets={at.code: Decimal(100) for at in account_types},
                # Note: Grand total targets are always 100% of the account type
            )
        )

        return rows

    def _format_money(self, val: Decimal) -> str:
        """Format decimal as money string: $1,234 or ($1,234)."""
        # Convert to float for formatting logic if needed, or keep decimal
        is_negative = val < 0
        abs_val = abs(val)
        s = f"${abs_val:,.0f}"
        return f"({s})" if is_negative else s

    def _build_row(
        self,
        label: str,
        ac_id: int,
        cat_code: str,
        row_values: pd.Series,
        account_types: list[Any],
        portfolio_total: Decimal,
        mode: str,
        ac_targets: dict[str, Decimal],  # Map of AT code -> Target % sum
        is_subtotal: bool = False,
        is_group_total: bool = False,
        is_grand_total: bool = False,
        is_cash: bool = False,
    ) -> AllocationTableRow:
        at_columns = []

        row_total_val = Decimal(float(row_values.sum()))
        row_target_val = Decimal(0)

        for at in account_types:
            # DataFrame columns are Account_Type Labels
            current_val = Decimal(float(row_values.get(at.label, 0.0)))
            at_total = getattr(at, "current_total_value", Decimal(0))

            # Target Calculation
            tgt_pct = ac_targets.get(at.code, Decimal(0))

            # If explicit input is percentage
            target_val = at_total * (tgt_pct / Decimal(100))

            variance_val = current_val - target_val

            if mode == "percent":
                current_pct = (current_val / at_total * 100) if at_total else Decimal(0)
                # target pct passed in is already relative to account type
                target_pct_display = tgt_pct
                variance_pct = current_pct - target_pct_display

                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=f"{current_pct:.1f}%",
                        target=f"{target_pct_display:.1f}%",
                        vtarget=f"{variance_pct:.1f}%",
                        current_raw=current_pct,
                        target_raw=target_pct_display,
                        vtarget_raw=variance_pct,
                    )
                )

                # Accumulate row target for portfolio column
                row_target_val += target_val

            else:  # money
                at_columns.append(
                    AccountTypeColumnData(
                        code=at.code,
                        label=at.label,
                        current=self._format_money(current_val),
                        target=self._format_money(target_val) if target_val > 0 else "--",
                        vtarget=self._format_money(variance_val),
                        current_raw=current_val,
                        target_raw=target_val,
                        vtarget_raw=variance_val,
                    )
                )
                row_target_val += target_val

        # Portfolio Columns
        if mode == "percent":
            current_pct = (row_total_val / portfolio_total * 100) if portfolio_total else Decimal(0)
            target_pct = (row_target_val / portfolio_total * 100) if portfolio_total else Decimal(0)
            variance_pct = current_pct - target_pct

            p_current = f"{current_pct:.1f}%"
            p_target = f"{target_pct:.1f}%"
            p_vtarget = f"{variance_pct:.1f}%"
        else:
            p_current = self._format_money(row_total_val)
            p_target = self._format_money(row_target_val)
            p_vtarget = self._format_money(row_total_val - row_target_val)

        return AllocationTableRow(
            asset_class_id=ac_id,
            asset_class_name=label,
            category_code=cat_code,
            is_subtotal=is_subtotal,
            is_group_total=is_group_total,
            is_grand_total=is_grand_total,
            is_cash=is_cash,
            account_type_data=at_columns,
            portfolio_current=p_current,
            portfolio_target=p_target,
            portfolio_vtarget=p_vtarget,
        )

    def _aggregate_targets(
        self, account_types: list[Any], ac_names_list: list[str], ac_meta: dict[str, Any]
    ) -> dict[str, Decimal]:
        # Sum target % for list of asset classes per account type
        # Note: this is strictly summing the percentages (e.g. 50% + 20% = 70% target for this category)
        res = {}
        for at in account_types:
            total_pct = Decimal(0)
            for ac in ac_names_list:
                aid = ac_meta[ac]["id"]
                total_pct += at.target_map.get(aid, Decimal(0))
            res[at.code] = total_pct
        return res

    def _build_empty_dashboard_rows(
        self, account_types: list[Any], portfolio_total: Decimal, mode: str
    ) -> list[AllocationTableRow]:
        # Minimal implementation for empty state
        return []

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

        result: dict[str, dict[int, dict[int, Decimal]]] = {
            "account_type": {},
            "account": {},
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

        # Iterate through hierarchy
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

        # Cash row
        cash_row = self._build_cash_row_presentation(
            df_portfolio=df_portfolio,
            df_account_type=df_account_type,
            df_account=df_account,
            accounts_by_type=accounts_by_type,
            portfolio_total=portfolio_total,
            mode=mode,
        )
        if cash_row:
            rows.append(cash_row)

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

            # Account type current
            at_current_dollars = 0.0
            at_current_pct = 0.0
            at_total_dollars = 0.0

            col_name = f"{ac_name}_dollars"
            if (
                not df_account_type.empty
                and type_label in df_account_type.index
                and col_name in df_account_type.columns
            ):
                at_current_dollars = float(df_account_type.loc[type_label, col_name])
                # Get account type total for percentage
                dollar_cols = [c for c in df_account_type.columns if c.endswith("_dollars")]
                at_total_dollars = float(df_account_type.loc[type_label, dollar_cols].sum())
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
                acc_total_dollars = 0.0

                if (
                    not df_account.empty
                    and acc_name in df_account.index
                    and col_name in df_account.columns
                ):
                    acc_current_dollars = float(df_account.loc[acc_name, col_name])
                    dollar_cols = [c for c in df_account.columns if c.endswith("_dollars")]
                    acc_total_dollars = float(df_account.loc[acc_name, dollar_cols].sum())
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
                    acc_variance_display = f"${acc_variance_dollars:+,.0f}"

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
                at_variance_display = f"${at_variance_dollars:+,.0f}"

            account_type_columns.append(
                {
                    "id": type_id,
                    "label": type_label,
                    "current": at_current_display,
                    "current_raw": at_current_dollars,
                    "target_input": at_target_input_pct if at_target_input_pct is not None else "",
                    "target_input_raw": at_target_input_pct if at_target_input_pct is not None else None,
                    "weighted_target": at_weighted_display,
                    "weighted_target_raw": at_weighted_target_dollars,
                    "variance": at_variance_display,
                    "variance_raw": at_variance_dollars,
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
            portfolio_variance_display = f"${portfolio_variance_dollars:+,.0f}"

        return {
            "row_type": "asset",
            "asset_class_id": ac_id,
            "asset_class_name": ac_name,
            "group_code": ac_meta["group_code"],
            "category_code": ac_meta["category_code"],
            "is_asset": True,
            "is_subtotal": False,
            "is_group_total": False,
            "is_grand_total": False,
            "is_cash": False,
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
                            "variance": f"${acc_variance:+,.0f}",
                            "variance_raw": acc_variance,
                        }
                    )

                account_type_columns.append(
                    {
                        "id": at["id"],
                        "label": at["label"],
                        "current": f"${at_current:,.0f}",
                        "current_raw": at_current,
                        "weighted_target": f"${at_weighted:,.0f}",
                        "weighted_target_raw": at_weighted,
                        "variance": f"${at_variance:+,.0f}",
                        "variance_raw": at_variance,
                        "accounts": account_columns,
                    }
                )

        return {
            "row_type": "subtotal",
            "asset_class_id": 0,
            "asset_class_name": f"{category_label} Total",
            "group_code": ac_metadata[asset_classes[0]]["group_code"],
            "category_code": category_code,
            "is_asset": False,
            "is_subtotal": True,
            "is_group_total": False,
            "is_grand_total": False,
            "is_cash": False,
            "css_class": "subtotal",
            "portfolio": {
                "current": f"${portfolio_current:,.0f}",
                "target": f"${portfolio_target:,.0f}",
                "variance": f"${portfolio_variance:+,.0f}",
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
        group_label = group_rows[0].get("group_code", "")

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
                                "variance": f"${acc_variance:+,.0f}",
                                "variance_raw": acc_variance,
                            }
                        )

                    account_type_columns.append(
                        {
                            "id": at["id"],
                            "label": at["label"],
                            "current": f"${at_current:,.0f}",
                            "current_raw": at_current,
                            "weighted_target": f"${at_weighted:,.0f}",
                            "weighted_target_raw": at_weighted,
                            "variance": f"${at_variance:+,.0f}",
                            "variance_raw": at_variance,
                            "accounts": account_columns,
                        }
                    )

        return {
            "row_type": "group_total",
            "asset_class_id": 0,
            "asset_class_name": f"{group_label} Total",
            "group_code": group_code,
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

    def _build_cash_row_presentation(
        self,
        df_portfolio: pd.DataFrame,
        df_account_type: pd.DataFrame,
        df_account: pd.DataFrame,
        accounts_by_type: dict[int, list[dict[str, Any]]],
        portfolio_total: float,
        mode: str,
    ) -> dict[str, Any] | None:
        """Build cash row with implicit remainder calculations."""
        # For now, return None - cash handling will be implemented in a future iteration
        # This is a placeholder to maintain the structure
        return None

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
            if r.get("is_asset") and not r.get("is_cash") and not r.get("is_subtotal") and not r.get("is_group_total")
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
                            "variance": acc_variance_display,
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
                        "label": at["label"],
                        "current": at_current_display,
                        "current_raw": at_current,
                        "weighted_target": at_weighted_display,
                        "weighted_target_raw": at_weighted,
                        "variance": at_variance_display,
                        "variance_raw": at_variance,
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

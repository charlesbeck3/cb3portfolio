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
            "portfolio_summary": self._calculate_portfolio_summary(
                holdings_df, total_value
            ),
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
        self,
        holdings_df: pd.DataFrame,
        effective_targets_map: dict[int, dict[str, Decimal]]
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
                target_records.append({'Account_ID': aid, 'Asset_Class': ac, 'Target_Pct': float(pct)})

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
            if r["Sec_Count"] > 0 else 0.0,
            axis=1
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
        df_by_at_ac = df_by_ac.groupby(level="Account_Type").sum() # Rows -> Account Type

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
        ac_qs = AssetClass.objects.select_related('category__parent').all()
        ac_meta = {
            ac.name: {
                'id': ac.id,
                'category_code': ac.category.code,
                'category_label': ac.category.label,
                'group_code': ac.category.parent.code if ac.category.parent else ac.category.code,
                'group_label': ac.category.parent.label if ac.category.parent else ac.category.label
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
             grp = str(meta['group_code'])
             cat = str(meta['category_code'])

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
                     if (ac, ac_meta[ac]['category_label']) in df_grid.index:
                        val += float(df_grid.loc[(ac, ac_meta[ac]['category_label'])].sum())
            group_totals[grp] = val

        sorted_groups = sorted(group_totals.keys(), key=lambda k: group_totals[k], reverse=True)

        for grp in sorted_groups:
            # Sort categories by total
            cat_totals = {}
            for cat, acs in hierarchy[grp].items():
                val = 0.0
                for ac in acs:
                    if (ac, ac_meta[ac]['category_label']) in df_grid.index:
                        val += float(df_grid.loc[(ac, ac_meta[ac]['category_label'])].sum())
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
                    if cash_asset_class_id and meta['id'] == cash_asset_class_id:
                        continue
                    if (ac, meta['category_label']) in df_grid.index:
                        ac_vals[ac] = float(df_grid.loc[(ac, meta['category_label'])].sum())

                sorted_acs = sorted(ac_vals.keys(), key=lambda k: ac_vals[k], reverse=True)

                for ac in sorted_acs:
                    # Build Asset Row
                    meta = ac_meta[ac]
                    idx = (ac, meta['category_label'])
                    row_values = df_grid.loc[idx] if idx in df_grid.index else pd.Series()

                    rows.append(self._build_row(
                        label=ac,
                        ac_id=cast(int, meta['id']),
                        cat_code=cat,
                        is_subtotal=False,
                        row_values=row_values,
                        account_types=account_types,
                        portfolio_total=portfolio_total_value,
                        mode=effective_mode,
                         # Pass map for targets logic
                        ac_targets={at.code: at.target_map.get(meta['id'], Decimal(0)) for at in account_types}
                    ))

                # Category Subtotal
                if len(sorted_acs) > 0 and len(hierarchy[grp][cat]) > 1:
                    # Calculate category total values
                    cat_acs = hierarchy[grp][cat]

                    cat_indices = [(a, ac_meta[a]['category_label']) for a in cat_acs
                                  if (not cash_asset_class_id or ac_meta[a]['id'] != cash_asset_class_id)
                                  and (a, ac_meta[a]['category_label']) in df_grid.index]

                    if cat_indices:
                        cat_values = df_grid.loc[cat_indices].sum(axis=0)
                        rows.append(self._build_row(
                           label=f"{ac_meta[cat_acs[0]]['category_label']} Total",
                           ac_id=0,
                           cat_code=cat,
                           is_subtotal=True,
                           row_values=cat_values,
                           account_types=account_types,
                           portfolio_total=portfolio_total_value,
                           mode=effective_mode,
                           ac_targets=self._aggregate_targets(account_types, cat_acs, ac_meta)
                        ))

            # Group Total
            if len(sorted_cats) > 1:
                 # Calculate group values
                 grp_acs = []
                 for c in hierarchy[grp].values():
                     grp_acs.extend(c)

                 grp_indices = [(a, ac_meta[a]['category_label']) for a in grp_acs
                               if (not cash_asset_class_id or ac_meta[a]['id'] != cash_asset_class_id)
                               and (a, ac_meta[a]['category_label']) in df_grid.index]

                 if grp_indices:
                     grp_values = df_grid.loc[grp_indices].sum(axis=0)
                     rows.append(self._build_row(
                        label=f"{ac_meta[grp_acs[0]]['group_label']} Total",
                        ac_id=0,
                        cat_code="",
                        is_subtotal=False,
                        is_group_total=True,
                        row_values=grp_values,
                        account_types=account_types,
                        portfolio_total=portfolio_total_value,
                        mode=effective_mode,
                        ac_targets=self._aggregate_targets(account_types, grp_acs, ac_meta)
                     ))

        # Cash Row
        if cash_asset_class_id:
            # Find cash AC name
            cash_ac_name = next((name for name, m in ac_meta.items() if m['id'] == cash_asset_class_id), None)
            if cash_ac_name:
                 meta = ac_meta[cash_ac_name]
                 idx = (cash_ac_name, meta['category_label'])
                 cash_values = df_grid.loc[idx] if idx in df_grid.index else pd.Series(0, index=df_grid.columns)

                 rows.append(self._build_cash_row(
                     cash_values=cash_values,
                     account_types=account_types,
                     portfolio_total=portfolio_total_value,
                     mode=effective_mode
                 ))

        # Grand Total
        # Sum entire grid
        grand_total_values = df_grid.sum(axis=0)
        rows.append(self._build_row(
            label="Total",
            ac_id=0,
            cat_code="",
            is_grand_total=True,
            row_values=grand_total_values,
            account_types=account_types,
            portfolio_total=portfolio_total_value,
            mode=effective_mode,
             # All targets
             ac_targets={at.code: Decimal(100) for at in account_types}
             # Note: Grand total targets are always 100% of the account type
        ))

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
        ac_targets: dict[str, Decimal], # Map of AT code -> Target % sum
        is_subtotal: bool = False,
        is_group_total: bool = False,
        is_grand_total: bool = False,
    ) -> AllocationTableRow:

        at_columns = []

        row_total_val = Decimal(float(row_values.sum()))
        row_target_val = Decimal(0)

        for at in account_types:
            # DataFrame columns are Account_Type Labels
            current_val = Decimal(float(row_values.get(at.label, 0.0)))
            at_total = getattr(at, 'current_total_value', Decimal(0))

            # Target Calculation
            tgt_pct = ac_targets.get(at.code, Decimal(0))

            # If explicit input is percentage
            target_val = at_total * (tgt_pct / Decimal(100))

            variance_val = current_val - target_val

            if mode == 'percent':
                current_pct = (current_val / at_total * 100) if at_total else Decimal(0)
                # target pct passed in is already relative to account type
                target_pct_display = tgt_pct
                variance_pct = current_pct - target_pct_display

                at_columns.append(AccountTypeColumnData(
                    code=at.code, label=at.label,
                    current=f"{current_pct:.1f}%",
                    target=f"{target_pct_display:.1f}%",
                    vtarget=f"{variance_pct:.1f}%",
                    current_raw=current_pct,
                    target_raw=target_pct_display,
                    vtarget_raw=variance_pct
                ))

                # Accumulate row target for portfolio column
                row_target_val += target_val

            else: # money
                 at_columns.append(AccountTypeColumnData(
                    code=at.code, label=at.label,
                    current=self._format_money(current_val),
                    target=self._format_money(target_val) if target_val > 0 else "--",
                    vtarget=self._format_money(variance_val),
                    current_raw=current_val,
                    target_raw=target_val,
                    vtarget_raw=variance_val
                ))
                 row_target_val += target_val

        # Portfolio Columns
        if mode == 'percent':
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
            is_cash=False,
            account_type_data=at_columns,
            portfolio_current=p_current,
            portfolio_target=p_target,
            portfolio_vtarget=p_vtarget
        )

    def _build_cash_row(
        self,
        cash_values: pd.Series,
        account_types: list[Any],
        portfolio_total: Decimal,
        mode: str,
    ) -> AllocationTableRow:
        # Cash target is implicit remainder.

        at_columns = []
        row_total_val = Decimal(float(cash_values.sum()))
        row_target_val = Decimal(0)

        for at in account_types:
            # DataFrame columns are Account_Type Labels
            current_val = Decimal(float(cash_values.get(at.label, 0.0)))
            at_total = getattr(at, 'current_total_value', Decimal(0))

            # Sum other targets
            total_other_targets = sum(at.target_map.values(), Decimal(0))
            cash_target_pct = Decimal(100) - total_other_targets
            if cash_target_pct < 0:
                cash_target_pct = Decimal(0)

            target_val = at_total * (cash_target_pct / Decimal(100))
            variance_val = current_val - target_val

            if mode == 'percent':
                current_pct = (current_val / at_total * 100) if at_total else Decimal(0)
                at_columns.append(AccountTypeColumnData(
                    code=at.code, label=at.label,
                    current=f"{current_pct:.1f}%",
                    target=f"{cash_target_pct:.1f}%",
                    vtarget=f"{(current_pct - cash_target_pct):.1f}%",
                    current_raw=current_pct,
                    target_raw=cash_target_pct,
                    vtarget_raw=current_pct - cash_target_pct
                ))
                row_target_val += target_val
            else:
                 at_columns.append(AccountTypeColumnData(
                    code=at.code, label=at.label,
                    current=self._format_money(current_val),
                    target=self._format_money(target_val),
                    vtarget=self._format_money(variance_val),
                    current_raw=current_val,
                    target_raw=target_val,
                    vtarget_raw=variance_val
                ))
                 row_target_val += target_val

        # Portfolio Columns
        if mode == 'percent':
             current_pct = (row_total_val / portfolio_total * 100) if portfolio_total else Decimal(0)
             target_pct = (row_target_val / portfolio_total * 100) if portfolio_total else Decimal(0)
             p_current = f"{current_pct:.1f}%"
             p_target = f"{target_pct:.1f}%"
             p_vtarget = f"{(current_pct - target_pct):.1f}%"
        else:
             p_current = self._format_money(row_total_val)
             p_target = self._format_money(row_target_val)
             p_vtarget = self._format_money(row_total_val - row_target_val)

        return AllocationTableRow(
            asset_class_id=0,
            asset_class_name="Cash",
            category_code="CASH",
            is_subtotal=False,
            is_group_total=False,
            is_grand_total=False,
            is_cash=True,
            account_type_data=at_columns,
            portfolio_current=p_current,
            portfolio_target=p_target,
            portfolio_vtarget=p_vtarget
        )

    def _aggregate_targets(self, account_types: list[Any], ac_names_list: list[str], ac_meta: dict[str, Any]) -> dict[str, Decimal]:
        # Sum target % for list of asset classes per account type
        # Note: this is strictly summing the percentages (e.g. 50% + 20% = 70% target for this category)
        res = {}
        for at in account_types:
            total_pct = Decimal(0)
            for ac in ac_names_list:
                aid = ac_meta[ac]['id']
                total_pct += at.target_map.get(aid, Decimal(0))
            res[at.code] = total_pct
        return res

    def _build_empty_dashboard_rows(self, account_types: list[Any], portfolio_total: Decimal, mode: str) -> list[AllocationTableRow]:
         # Minimal implementation for empty state
         return []

    def _empty_allocations(self) -> dict[str, pd.DataFrame]:
        """Return empty DataFrames for empty portfolio."""
        return {
            "by_account": pd.DataFrame(),
            "by_account_type": pd.DataFrame(),
            "by_asset_class": pd.DataFrame(),
            "portfolio_summary": pd.DataFrame(),
        }

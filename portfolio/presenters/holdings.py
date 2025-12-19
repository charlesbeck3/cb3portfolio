from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from portfolio.templatetags.portfolio_filters import (
    accounting_amount,
    accounting_number,
    accounting_percent,
    percentage_of,
)


@dataclass(frozen=True)
class HoldingsTableRow:
    ticker: str
    name: str
    asset_class: str
    category_code: str
    row_type: str  # 'holding', 'subtotal', 'group_total', 'grand_total'
    row_id: str  # Unique ID for collapse toggling
    parent_id: str  # ID of parent row for collapse toggling
    row_class: str  # CSS classes for the row

    # Price
    price: str
    price_raw: Decimal

    # Shares
    shares: str
    shares_raw: Decimal
    target_shares: str
    target_shares_raw: Decimal
    shares_variance: str
    shares_variance_raw: Decimal

    # Value
    value: str
    value_raw: Decimal
    target_value: str
    target_value_raw: Decimal
    value_variance: str
    value_variance_raw: Decimal

    # Allocation
    allocation: str
    allocation_raw: Decimal
    target_allocation: str
    target_allocation_raw: Decimal
    allocation_variance: str
    allocation_variance_raw: Decimal

    is_holding: bool = False
    is_subtotal: bool = False
    is_group_total: bool = False
    is_grand_total: bool = False


class HoldingsTableBuilder:
    def build_rows(
        self,
        holdings_detail_df: Any,  # pd.DataFrame
        ac_meta: dict[str, Any],
    ) -> list[HoldingsTableRow]:
        rows: list[HoldingsTableRow] = []
        df = holdings_detail_df

        if df.empty:
            return []

        # Calculate Grand Total
        grand_total = Decimal(float(df["Value"].sum()))
        grand_total_target = Decimal(float(df["Target_Value"].sum()))

        # We need to determine Groups and Categories order
        # We can use the DataFrame's Asset_Category column, but we need Group info.
        # ac_meta maps Asset_Class Name -> {group_code, group_label, category_code, category_label}

        # Add metadata columns to DF for easier grouping
        # Map AC Name to Group Code/Label
        def get_meta(ac_name: str, key: str) -> str:
            return ac_meta.get(ac_name, {}).get(key, "")

        df["Group_Code"] = df["Asset_Class"].apply(lambda x: get_meta(x, "group_code"))
        df["Group_Label"] = df["Asset_Class"].apply(lambda x: get_meta(x, "group_label"))
        df["Category_Code"] = df["Asset_Class"].apply(lambda x: get_meta(x, "category_code"))
        df["Category_Label"] = df["Asset_Class"].apply(
            lambda x: get_meta(x, "category_label")
        )  # Use hierarchy label or DF label? metadata is safer.

        # Sort Order: Group Label (or priority?), Category Label, Asset Class?, Ticker
        # We don't have explicit sort order here easily unless we passed it.
        # Let's assume alphanumeric sort for now or rely on what comes from `ac_meta` if we iterate that instead?
        # Iterating the DF is easier for data aggregations.

        # Assign a Sort Key if possible. To keep it simple, we sort by Group Label, Category Label, Ticker.
        df.sort_values(["Group_Label", "Category_Label", "Ticker"], inplace=True)

        # Group by Group -> Category
        for group_label, group_df in df.groupby("Group_Label", sort=False):
            # We need a group code for ID.
            group_code = group_df.iloc[0]["Group_Code"]
            group_row_id = f"group-{group_code}"

            # Category Loop
            for cat_label, cat_df in group_df.groupby("Category_Label", sort=False):
                cat_code = cat_df.iloc[0]["Category_Code"]

                # Holdings Loop
                # Aggregating by Ticker within Filter (if account specific?)
                # The DF rows are per-account-holding.
                # If we are viewing a specific account, rows are unique by ticker.
                # If viewing ALL accounts, we see duplicates tickers?
                # The legacy view aggregated by Ticker across accounts.
                # `calculate_holdings_detail` returns rows per account.

                # We need to Aggregate by Ticker for the Main View!
                # Group by Ticker within this category bucket
                ticker_groups = cat_df.groupby("Ticker")

                for ticker, t_df in ticker_groups:
                    # Sum values for this ticker across accounts
                    val = Decimal(float(t_df["Value"].sum()))
                    tgt_val = Decimal(float(t_df["Target_Value"].sum()))
                    shares = Decimal(float(t_df["Shares"].sum()))
                    # Target shares? Sum of target_shares_per_holding?
                    # calculate_holdings_detail doesn't calculate target_shares yet, only value.
                    # We can calc it here: Target Value / Price
                    price = Decimal(float(t_df["Price"].iloc[0]))  # Assume same price

                    tgt_shares = tgt_val / price if price else Decimal(0)

                    rows.append(
                        self._build_holding_row(
                            ticker=ticker,
                            name=t_df.iloc[0]["Security_Name"]
                            if "Security_Name" in t_df.columns
                            else ticker,  # Security Name not in DF yet?
                            # Wait, calculate_holdings_detail doesn't define Security_Name?
                            # Models `to_dataframe` has Security (ticker). It doesn't have name.
                            # Legacy struct had name. We might need to fetch it or drop it.
                            # Ticker is usually sufficient or we can join.
                            asset_class=t_df.iloc[0]["Asset_Class"],
                            category_code=cat_code,
                            parent_id=group_row_id,
                            portfolio_total=grand_total,
                            val=val,
                            tgt_val=tgt_val,
                            shares=shares,
                            tgt_shares=tgt_shares,
                            price=price,
                        )
                    )

                # Category Subtotal
                if (
                    len(group_df["Category_Label"].unique()) > 1 or len(group_df) > 1
                ):  # Logic: Show subtotal if useful
                    # Sum category
                    cat_val = Decimal(float(cat_df["Value"].sum()))
                    cat_tgt = Decimal(float(cat_df["Target_Value"].sum()))

                    rows.append(
                        self._build_category_subtotal_row(
                            label=cat_label,
                            category_code=cat_code,
                            parent_id=group_row_id,
                            portfolio_total=grand_total,
                            val=cat_val,
                            tgt_val=cat_tgt,
                        )
                    )

            # Group Total
            grp_val = Decimal(float(group_df["Value"].sum()))
            grp_tgt = Decimal(float(group_df["Target_Value"].sum()))

            rows.append(
                self._build_group_total_row(
                    label=group_label,
                    group_code=group_code,
                    row_id=group_row_id,
                    portfolio_total=grand_total,
                    val=grp_val,
                    tgt_val=grp_tgt,
                )
            )

        # Grand Total
        rows.append(self._build_grand_total_row(grand_total, grand_total_target))

        return rows

    def _build_holding_row(
        self,
        ticker: str,
        name: str,
        asset_class: str,
        category_code: str,
        parent_id: str,
        portfolio_total: Decimal,
        val: Decimal,
        tgt_val: Decimal,
        shares: Decimal,
        tgt_shares: Decimal,
        price: Decimal,
    ) -> HoldingsTableRow:
        val_var = val - tgt_val
        shares_var = shares - tgt_shares

        alloc = percentage_of(val, portfolio_total)
        tgt_alloc = percentage_of(tgt_val, portfolio_total)
        alloc_var = alloc - tgt_alloc

        return HoldingsTableRow(
            ticker=ticker,
            name=name,
            asset_class=asset_class,
            category_code=category_code,
            row_type="holding",
            row_id="",
            parent_id=parent_id,
            row_class=f"{parent_id}-rows collapse show",
            price=str(accounting_amount(price, 2)),
            price_raw=price,
            shares=f"{shares:.4f}",
            shares_raw=shares,
            target_shares=f"{tgt_shares:.2f}",
            target_shares_raw=tgt_shares,
            shares_variance=str(accounting_number(shares_var, 2)),
            shares_variance_raw=shares_var,
            value=str(accounting_amount(val, 0)),
            value_raw=val,
            target_value=str(accounting_amount(tgt_val, 0)),
            target_value_raw=tgt_val,
            value_variance=str(accounting_amount(val_var, 0)),
            value_variance_raw=val_var,
            allocation=f"{alloc:.2f}%",
            allocation_raw=alloc,
            target_allocation=f"{tgt_alloc:.2f}%",
            target_allocation_raw=tgt_alloc,
            allocation_variance=str(accounting_percent(alloc_var, 2)),
            allocation_variance_raw=alloc_var,
            is_holding=True,
        )

    def _build_category_subtotal_row(
        self,
        label: str,
        category_code: str,
        parent_id: str,
        portfolio_total: Decimal,
        val: Decimal,
        tgt_val: Decimal,
    ) -> HoldingsTableRow:
        val_var = val - tgt_val

        alloc = percentage_of(val, portfolio_total)
        tgt_alloc = percentage_of(tgt_val, portfolio_total)
        alloc_var = alloc - tgt_alloc

        return HoldingsTableRow(
            ticker="",
            name=f"{label} Total",
            asset_class="",
            category_code=category_code,
            row_type="subtotal",
            row_id="",
            parent_id=parent_id,
            row_class=f"table-secondary fw-bold {parent_id}-rows collapse show",
            price="",
            price_raw=Decimal(0),
            shares="",
            shares_raw=Decimal(0),
            target_shares="",
            target_shares_raw=Decimal(0),
            shares_variance="",
            shares_variance_raw=Decimal(0),
            value=str(accounting_amount(val, 0)),
            value_raw=val,
            target_value=str(accounting_amount(tgt_val, 0)),
            target_value_raw=tgt_val,
            value_variance=str(accounting_amount(val_var, 0)),
            value_variance_raw=val_var,
            allocation=f"{alloc:.2f}%",
            allocation_raw=alloc,
            target_allocation=f"{tgt_alloc:.2f}%",
            target_allocation_raw=tgt_alloc,
            allocation_variance=str(accounting_percent(alloc_var, 2)),
            allocation_variance_raw=alloc_var,
            is_subtotal=True,
        )

    def _build_group_total_row(
        self,
        label: str,
        group_code: str,
        row_id: str,
        portfolio_total: Decimal,
        val: Decimal,
        tgt_val: Decimal,
    ) -> HoldingsTableRow:
        val_var = val - tgt_val

        alloc = percentage_of(val, portfolio_total)
        tgt_alloc = percentage_of(tgt_val, portfolio_total)
        alloc_var = alloc - tgt_alloc

        return HoldingsTableRow(
            ticker="",
            name=f"{label} Total",
            asset_class="",
            category_code="",
            row_type="group_total",
            row_id=row_id,
            parent_id="",
            row_class="table-primary fw-bold border-top group-toggle mt-3",
            price="",
            price_raw=Decimal(0),
            shares="",
            shares_raw=Decimal(0),
            target_shares="",
            target_shares_raw=Decimal(0),
            shares_variance="",
            shares_variance_raw=Decimal(0),
            value=str(accounting_amount(val, 0)),
            value_raw=val,
            target_value=str(accounting_amount(tgt_val, 0)),
            target_value_raw=tgt_val,
            value_variance=str(accounting_amount(val_var, 0)),
            value_variance_raw=val_var,
            allocation=f"{alloc:.2f}%",
            allocation_raw=alloc,
            target_allocation=f"{tgt_alloc:.2f}%",
            target_allocation_raw=tgt_alloc,
            allocation_variance=str(accounting_percent(alloc_var, 2)),
            allocation_variance_raw=alloc_var,
            is_group_total=True,
        )

    def _build_grand_total_row(self, val: Decimal, tgt_val: Decimal) -> HoldingsTableRow:
        val_var = val - tgt_val

        # Allocations for Grand Total are 100% / 100% / 0%
        alloc = Decimal(100)
        tgt_alloc = Decimal(100)
        alloc_var = Decimal(0)

        return HoldingsTableRow(
            ticker="",
            name="Grand Total",
            asset_class="",
            category_code="",
            row_type="grand_total",
            row_id="",
            parent_id="",
            row_class="table-dark fw-bold",
            price="",
            price_raw=Decimal(0),
            shares="",
            shares_raw=Decimal(0),
            target_shares="",
            target_shares_raw=Decimal(0),
            shares_variance="",
            shares_variance_raw=Decimal(0),
            value=str(accounting_amount(val, 0)),
            value_raw=val,
            target_value=str(accounting_amount(tgt_val, 0)),
            target_value_raw=tgt_val,
            value_variance=str(accounting_amount(val_var, 0)),
            value_variance_raw=val_var,
            allocation=f"{alloc:.2f}%",
            allocation_raw=alloc,
            target_allocation=f"{tgt_alloc:.2f}%",
            target_allocation_raw=tgt_alloc,
            allocation_variance=str(accounting_percent(alloc_var, 2)),
            allocation_variance_raw=alloc_var,
            is_grand_total=True,
        )

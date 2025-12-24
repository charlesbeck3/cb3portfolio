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
        """
        Build HoldingsTableRow objects for the holdings table.

        REFACTORED: Uses vectorized aggregation to avoid nested loops.
        """
        df = holdings_detail_df
        if df.empty:
            return []

        # Step 1: Pre-aggregate all hierarchical levels (VECTORIZED)
        aggregated = self._aggregate_holdings_data(df, ac_meta)

        # Step 2: Calculate grand totals for percentages
        grand_total = Decimal(float(df["Value"].sum()))
        grand_total_target = Decimal(float(df["Target_Value"].sum()))

        # Step 3: Convert aggregated DataFrames to row objects
        rows = []

        # Process holdings
        for _, row_data in aggregated["holdings"].iterrows():
            rows.append(self._build_row_from_data(row_data, grand_total, "holding"))

        # Process category subtotals
        for _, row_data in aggregated["categories"].iterrows():
            rows.append(self._build_row_from_data(row_data, grand_total, "subtotal"))

        # Process group totals
        for _, row_data in aggregated["groups"].iterrows():
            rows.append(self._build_row_from_data(row_data, grand_total, "group_total"))

        # Process grand total
        rows.append(self._build_grand_total_row(grand_total, grand_total_target))

        # Step 4: Reorder rows hierarchically (assets -> subtotal -> group total -> grand total)
        return self._reorder_rows_hierarchically(rows, aggregated)

    def _aggregate_holdings_data(
        self,
        df: Any,
        ac_meta: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Pre-aggregate holdings at all hierarchical levels using vectorized operations.
        """

        df = df.copy()

        # Add metadata columns (VECTORIZED)
        df["Group_Code"] = df["Asset_Class"].map(lambda x: ac_meta.get(x, {}).get("group_code", ""))
        df["Group_Label"] = df["Asset_Class"].map(
            lambda x: ac_meta.get(x, {}).get("group_label", "")
        )
        df["Category_Code"] = df["Asset_Class"].map(
            lambda x: ac_meta.get(x, {}).get("category_code", "")
        )
        df["Category_Label"] = df["Asset_Class"].map(
            lambda x: ac_meta.get(x, {}).get("category_label", "")
        )

        # 1. Aggregate by Ticker (Holdings)
        # We group by Group/Category/Asset_Class/Ticker to keep hierarchy info
        ticker_agg = (
            df.groupby(
                [
                    "Group_Code",
                    "Group_Label",
                    "Category_Code",
                    "Category_Label",
                    "Asset_Class",
                    "Ticker",
                ]
            )
            .agg({"Value": "sum", "Target_Value": "sum", "Shares": "sum", "Price": "first"})
            .reset_index()
        )

        # 2. Aggregate by Category (Subtotals)
        cat_agg = (
            df.groupby(["Group_Code", "Group_Label", "Category_Code", "Category_Label"])
            .agg({"Value": "sum", "Target_Value": "sum"})
            .reset_index()
        )

        # 3. Aggregate by Group (Totals)
        grp_agg = (
            df.groupby(["Group_Code", "Group_Label"])
            .agg({"Value": "sum", "Target_Value": "sum"})
            .reset_index()
        )

        return {
            "holdings": ticker_agg,
            "categories": cat_agg,
            "groups": grp_agg,
        }

    def _build_row_from_data(
        self,
        row_data: Any,
        portfolio_total: Decimal,
        row_type: str,
    ) -> HoldingsTableRow:
        """Helper to build a row object from aggregated Series/dict data."""
        val = Decimal(float(row_data["Value"]))
        tgt_val = Decimal(float(row_data["Target_Value"]))

        if row_type == "holding":
            ticker = row_data["Ticker"]
            price = Decimal(float(row_data["Price"]))
            shares = Decimal(float(row_data["Shares"]))
            tgt_shares = tgt_val / price if price else Decimal(0)
            return self._build_holding_row(
                ticker=ticker,
                name=ticker,  # Could join with security name but ticker is default
                asset_class=row_data["Asset_Class"],
                category_code=row_data["Category_Code"],
                parent_id=f"group-{row_data['Group_Code']}",
                portfolio_total=portfolio_total,
                val=val,
                tgt_val=tgt_val,
                shares=shares,
                tgt_shares=tgt_shares,
                price=price,
            )
        elif row_type == "subtotal":
            return self._build_category_subtotal_row(
                label=row_data["Category_Label"],
                category_code=row_data["Category_Code"],
                parent_id=f"group-{row_data['Group_Code']}",
                portfolio_total=portfolio_total,
                val=val,
                tgt_val=tgt_val,
            )
        else:  # group_total
            return self._build_group_total_row(
                label=row_data["Group_Label"],
                group_code=row_data["Group_Code"],
                row_id=f"group-{row_data['Group_Code']}",
                portfolio_total=portfolio_total,
                val=val,
                tgt_val=tgt_val,
            )

    def _reorder_rows_hierarchically(
        self,
        rows: list[HoldingsTableRow],
        aggregated: dict[str, Any],
    ) -> list[HoldingsTableRow]:
        """
        Reorder rows to match hierarchical requirements:
        Assets -> Category Subtotal -> Group Total -> Grand Total
        """
        # Index rows for fast lookup
        holdings = [r for r in rows if r.is_holding]
        subtotals = [r for r in rows if r.is_subtotal]
        group_totals = [r for r in rows if r.is_group_total]
        grand_total = [r for r in rows if r.is_grand_total]

        from collections import defaultdict

        h_by_cat = defaultdict(list)
        for h in holdings:
            h_by_cat[h.category_code].append(h)

        s_by_cat = {s.category_code: s for s in subtotals}

        # Need Group -> Category mapping from aggregated data
        from collections import defaultdict

        g_to_c = defaultdict(set)
        for _, r in aggregated["categories"].iterrows():
            g_to_c[r["Group_Code"]].add(r["Category_Code"])

        g_by_code = {g.row_id.replace("group-", ""): g for g in group_totals}

        result = []
        # Iterate Groups (sorted by Code or Label)
        for g_code in sorted(g_by_code.keys()):
            # Process Categories in this Group
            for c_code in sorted(g_to_c[g_code]):
                # Add holdings
                result.extend(sorted(h_by_cat[c_code], key=lambda x: x.ticker))
                # Add subtotal if exists
                if c_code in s_by_cat:
                    result.append(s_by_cat[c_code])

            # Add group total
            result.append(g_by_code[g_code])

        # Add grand total
        result.extend(grand_total)

        return result

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

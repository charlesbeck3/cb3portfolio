from __future__ import annotations

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
        self, holding_groups: dict[str, Any], grand_total_data: dict[str, Any]
    ) -> list[HoldingsTableRow]:
        rows: list[HoldingsTableRow] = []
        grand_total = grand_total_data.get("total", Decimal("0.00"))

        # Iterate over groups
        for group_code, group_data in holding_groups.items():
            group_row_id = f"group-{group_code}"

            # Categories in group
            for category_code, category_data in group_data.categories.items():
                # Holdings in category
                for holding in category_data.holdings:
                    rows.append(self._build_holding_row(holding, group_row_id, grand_total))

                if len(group_data.categories) > 1:
                    rows.append(
                        self._build_category_subtotal_row(
                            category_data, category_code, group_row_id, grand_total
                        )
                    )

            rows.append(
                self._build_group_total_row(group_data, group_code, group_row_id, grand_total)
            )

        # Grand Total
        rows.append(self._build_grand_total_row(grand_total_data))

        return rows

    def _build_holding_row(
        self, holding: Any, parent_id: str, portfolio_total: Decimal
    ) -> HoldingsTableRow:
        val = holding.value
        tgt_val = holding.target_value
        val_var = val - tgt_val

        shares = holding.shares
        tgt_shares = holding.target_shares
        shares_var = shares - tgt_shares

        alloc = percentage_of(val, portfolio_total)
        tgt_alloc = percentage_of(tgt_val, portfolio_total)
        alloc_var = alloc - tgt_alloc

        return HoldingsTableRow(
            ticker=holding.ticker,
            name=holding.name,
            asset_class=holding.asset_class,
            category_code=holding.category_code,
            row_type="holding",
            row_id="",
            parent_id=parent_id,
            row_class=f"{parent_id}-rows collapse show",
            price=str(accounting_amount(holding.current_price or Decimal(0), 2)),
            price_raw=holding.current_price or Decimal(0),
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
        category_data: Any,
        category_code: str,
        parent_id: str,
        portfolio_total: Decimal,
    ) -> HoldingsTableRow:
        val = category_data.total
        tgt_val = category_data.total_target_value
        val_var = val - tgt_val

        alloc = percentage_of(val, portfolio_total)
        tgt_alloc = percentage_of(tgt_val, portfolio_total)
        alloc_var = alloc - tgt_alloc

        return HoldingsTableRow(
            ticker="",
            name=f"{category_data.label} Total",
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
        self, group_data: Any, group_code: str, row_id: str, portfolio_total: Decimal
    ) -> HoldingsTableRow:
        val = group_data.total
        tgt_val = group_data.total_target_value
        val_var = val - tgt_val

        alloc = percentage_of(val, portfolio_total)
        tgt_alloc = percentage_of(tgt_val, portfolio_total)
        alloc_var = alloc - tgt_alloc

        return HoldingsTableRow(
            ticker="",
            name=f"{group_data.label} Total",
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

    def _build_grand_total_row(self, grand_total_data: dict[str, Any]) -> HoldingsTableRow:
        val = grand_total_data["total"]
        tgt_val = grand_total_data["target"]
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

"""
Tests for allocation presentation formatting.

Tests: portfolio/services/allocation_presentation.py
"""

from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from portfolio.services.allocation_presentation import AllocationPresentationFormatter


@pytest.mark.services
@pytest.mark.presentation
class TestAllocationPresentationFormatter:
    """Test the formatting of calculation results for display."""

    @pytest.fixture
    def formatter(self) -> AllocationPresentationFormatter:
        return AllocationPresentationFormatter()

    def test_format_value_percent_mode(self, formatter: AllocationPresentationFormatter) -> None:
        """Verify percent formatting."""
        assert formatter._format_value(42.5, "percent") == "42.5%"
        assert formatter._format_value(0.0, "percent") == "0.0%"

    def test_format_value_dollar_mode(self, formatter: AllocationPresentationFormatter) -> None:
        """Verify dollar formatting."""
        assert formatter._format_value(1234.56, "dollar") == "$1,235"
        assert formatter._format_value(0.0, "dollar") == "$0"

    def test_format_variance_with_sign(self, formatter: AllocationPresentationFormatter) -> None:
        """Verify variance formatting includes sign."""
        assert formatter._format_variance(5.2, "percent") == "+5.2%"
        assert formatter._format_variance(-3.1, "percent") == "-3.1%"
        assert formatter._format_variance(0.0, "percent") == "+0.0%"

    def test_format_money_accounting_style(
        self, formatter: AllocationPresentationFormatter
    ) -> None:
        """Verify money formatting uses accounting style for negatives."""
        assert formatter._format_money(Decimal("1234.56")) == "$1,235"
        assert formatter._format_money(Decimal("-1234.56")) == "($1,235)"

    def test_format_presentation_rows_structure(
        self, formatter: AllocationPresentationFormatter
    ) -> None:
        """Verify formatted rows have correct structure."""
        asset_data = {
            "group_code": ["EQUITY"],
            "category_code": ["US"],
            "asset_class_name": ["US Equities"],
            "asset_class_id": [1],
            "group_label": ["Equities"],
            "category_label": ["US Equities"],
            "is_cash": [False],
            "row_type": ["asset"],
            "portfolio_actual": [100.0],
            "portfolio_actual_pct": [10.0],
            "portfolio_effective": [120.0],
            "portfolio_effective_pct": [12.0],
            "portfolio_effective_variance": [-20.0],
            "portfolio_effective_variance_pct": [-2.0],
        }

        df_assets = pd.DataFrame(asset_data)
        df_assets = df_assets.set_index(["group_code", "category_code", "asset_class_name"])

        aggregated = {
            "assets": df_assets,
            "category_subtotals": pd.DataFrame(),
            "group_totals": pd.DataFrame(),
            "grand_total": pd.DataFrame(),
        }

        accounts_by_type: dict[int, list[dict[str, Any]]] = {}
        target_strategies: dict[str, Any] = {"at_strategy_map": {}, "acc_strategy_map": {}}

        result = formatter.format_presentation_rows(
            aggregated_data=aggregated,
            accounts_by_type=accounts_by_type,
            target_strategies=target_strategies,
            mode="percent",
        )

        assert isinstance(result, list)
        assert len(result) == 1
        row = result[0]
        assert row["asset_class_name"] == "US Equities"
        assert isinstance(row["portfolio"]["actual"], str)
        assert "%" in row["portfolio"]["actual"]

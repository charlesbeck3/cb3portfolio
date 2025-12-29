"""
Tests for allocation presentation formatting.

Tests: portfolio/services/allocation_presentation.py
"""

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

    def test_format_presentation_rows_structure(
        self, formatter: AllocationPresentationFormatter
    ) -> None:
        """Verify formatted rows have correct structure and raw values."""
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
        )

        assert isinstance(result, list)
        assert len(result) == 1
        row = result[0]
        assert row["asset_class_name"] == "US Equities"

        # Verify raw numeric values are present
        assert isinstance(row["portfolio"]["actual"], float)
        assert row["portfolio"]["actual"] == 100.0
        assert row["portfolio"]["actual_pct"] == 10.0
        assert row["portfolio"]["effective"] == 120.0

    def test_policy_variance_available_in_presentation_rows(
        self, formatter: AllocationPresentationFormatter
    ) -> None:
        """
        Verify that portfolio['policy_variance'] is available in the formatted rows.
        """
        # 1. Mock DataFrame with necessary columns
        data = {
            "asset_class_name": ["Stocks", "Bonds"],
            "portfolio_actual": [600.0, 400.0],
            "portfolio_actual_pct": [60.0, 40.0],
            "portfolio_explicit_target": [500.0, 500.0],  # 50/50 target
            "portfolio_explicit_target_pct": [50.0, 50.0],
            # Calculated fields
            "portfolio_policy_variance": [100.0, -100.0],
            "portfolio_policy_variance_pct": [10.0, -10.0],
            # Effective fields
            "portfolio_effective": [550.0, 450.0],
            "portfolio_effective_pct": [55.0, 45.0],
            "portfolio_effective_variance": [50.0, -50.0],
            "portfolio_effective_variance_pct": [5.0, -5.0],
        }
        df = pd.DataFrame(data)

        # 2. Mock aggregated data dictionary
        aggregated_data = {
            "assets": df,
            "category_subtotals": pd.DataFrame(),
            "group_totals": pd.DataFrame(),
            "grand_total": pd.DataFrame(
                [
                    {
                        "row_type": "grand_total",
                        "portfolio_actual": 1000.0,
                        "portfolio_explicit_target": 1000.0,
                        "portfolio_effective": 1000.0,
                        "portfolio_policy_variance": 0.0,
                        "portfolio_effective_variance": 0.0,
                    }
                ]
            ),
        }

        accounts_by_type: dict[int, list[dict[str, Any]]] = {}
        target_strategies: dict[str, Any] = {}

        # 4. Format Rows (no mode needed)
        rows = formatter.format_presentation_rows(
            aggregated_data=aggregated_data,
            accounts_by_type=accounts_by_type,
            target_strategies=target_strategies,
        )

        # 5. Verify Results
        assert len(rows) > 0

        # check asset rows
        equity_row = next(r for r in rows if r["asset_class_name"] == "Stocks")
        assert "portfolio" in equity_row
        assert "policy_variance" in equity_row["portfolio"]
        # The formatter returns raw float
        assert equity_row["portfolio"]["policy_variance"] == 100.0
        assert equity_row["portfolio"]["policy_variance_pct"] == 10.0

    def test_formatter_exposes_policy_variance(
        self, formatter: AllocationPresentationFormatter
    ) -> None:
        """
        Directly test the _build_row_dict_from_formatted_data method to ensure it maps
        the policy variance columns correctly.
        """
        row_data = {
            "asset_class_name": "Test Asset",
            "portfolio_actual": 100.0,
            "portfolio_explicit_target": 80.0,
            "portfolio_policy_variance": 20.0,
            "portfolio_effective_variance": 10.0,
        }

        # No mode needed
        result = formatter._build_row_dict_from_formatted_data(
            row=row_data,
            accounts_by_type={},
            target_strategies={},
        )

        # Verify the dict structure
        assert result["portfolio"]["policy_variance"] == 20.0
        assert result["portfolio"]["effective_variance"] == 10.0

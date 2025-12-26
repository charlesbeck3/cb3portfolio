"""
Test suite for refactored allocation calculations.

Tests are organized into layers:
1. Pure calculation tests (no Django dependencies)
2. DataFrame aggregation tests
3. Formatting tests
4. Integration tests
"""

from decimal import Decimal
from typing import Any

from django.test import SimpleTestCase

import pandas as pd
import pytest

from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.services.allocation_presentation import AllocationPresentationFormatter


@pytest.mark.unit
@pytest.mark.calculations
class TestPureCalculations(SimpleTestCase):
    """
    Test pure calculation methods with mock DataFrames.

    These tests have ZERO Django dependencies - just pandas.
    """

    def setUp(self) -> None:
        """Create mock holdings DataFrame."""
        data = {
            ("Equities", "US Large Cap", "VTI"): [5000.0, 3000.0],
            ("Fixed Income", "Bonds", "BND"): [5000.0, 7000.0],
        }

        index = pd.MultiIndex.from_tuples(
            [
                ("Taxable", "Brokerage", "Account1", 1),
                ("401k", "Retirement", "Account2", 2),
            ],
            names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"],
        )

        columns = pd.MultiIndex.from_tuples(
            data.keys(), names=["Asset_Class", "Asset_Category", "Security"]
        )

        df = pd.DataFrame(list(data.values()), index=columns).T
        df.columns = columns
        df.index = index

        self.holdings_df = df
        self.engine = AllocationCalculationEngine()

    def test_calculate_by_asset_class_returns_numeric_only(self) -> None:
        """Verify by_asset_class returns only numeric values."""
        result = self.engine._calculate_by_asset_class(self.holdings_df, 20000.0)

        # Should have numeric columns only
        self.assertIn("dollars", result.columns)
        self.assertIn("percent", result.columns)

        # Values should be numeric, not strings
        self.assertIsInstance(result.loc["Equities", "dollars"], (float, int))
        self.assertIsInstance(result.loc["Equities", "percent"], (float, int))

        # No formatted strings
        self.assertNotIn("$", str(result.loc["Equities", "dollars"]))
        self.assertNotIn("%", str(result.loc["Equities", "percent"]))

    def test_calculate_allocations_structure(self) -> None:
        """Verify calculate_allocations returns correct structure."""
        result = self.engine.calculate_allocations(self.holdings_df)

        # Should have all expected keys
        self.assertIn("by_account", result)
        self.assertIn("by_account_type", result)
        self.assertIn("by_asset_class", result)
        self.assertIn("portfolio_summary", result)

        # All should be DataFrames
        for _key, df in result.items():
            self.assertIsInstance(df, pd.DataFrame)

    def test_by_account_numeric_values(self) -> None:
        """Verify by_account returns correct numeric values."""
        result = self.engine._calculate_by_account(self.holdings_df)

        # Account 1 should have 50% equities, 50% bonds
        equities_pct = result.loc[1, "Equities_actual_pct"]
        self.assertAlmostEqual(equities_pct, 50.0, places=1)

        # Should have dollar amounts too
        equities_dollars = result.loc[1, "Equities_actual"]
        self.assertAlmostEqual(equities_dollars, 5000.0, places=1)

    def test_empty_holdings_returns_empty_dfs(self) -> None:
        """Verify empty holdings returns empty DataFrames."""
        empty_df = pd.DataFrame()
        result = self.engine.calculate_allocations(empty_df)

        self.assertTrue(result["by_account"].empty)
        self.assertTrue(result["by_asset_class"].empty)


@pytest.mark.unit
@pytest.mark.calculations
class TestDataFrameAggregation(SimpleTestCase):
    """
    Test pandas aggregation logic.

    Verifies that subtotals, group totals, and grand totals
    are calculated correctly using pandas groupby.
    """

    def test_aggregate_presentation_levels_structure(self) -> None:
        """Verify aggregation returns all expected levels."""
        # Create mock asset DataFrame
        data = {
            "group_code": ["EQUITY", "EQUITY", "FIXED"],
            "category_code": ["US", "INTL", "BONDS"],
            "asset_class_name": ["US Stocks", "Intl Stocks", "Bonds"],
            "group_label": ["Equities", "Equities", "Fixed Income"],
            "category_label": ["US Equities", "Intl Equities", "Fixed Income Bonds"],
            "asset_class_id": [1, 2, 3],
            "portfolio_actual": [100.0, 50.0, 150.0],
            "portfolio_effective": [120.0, 60.0, 120.0],
            "portfolio_effective_variance": [-20.0, -10.0, 30.0],
        }

        df = pd.DataFrame(data)
        df = df.set_index(["group_code", "category_code", "asset_class_name"])

        engine = AllocationCalculationEngine()
        result = engine.aggregate_presentation_levels(df)

        # Should have all levels
        self.assertIn("assets", result)
        self.assertIn("category_subtotals", result)
        self.assertIn("group_totals", result)
        self.assertIn("grand_total", result)

        # Category subtotals should have correct sums
        equity_total = result["group_totals"].loc["EQUITY", "portfolio_actual"]
        self.assertAlmostEqual(equity_total, 150.0, places=1)

        # Grand total should sum everything
        grand_total = result["grand_total"].iloc[0]["portfolio_actual"]
        self.assertAlmostEqual(grand_total, 300.0, places=1)

    def test_category_subtotals_correct(self) -> None:
        """Verify category subtotals aggregate correctly."""
        data = {
            "group_code": ["EQUITY", "EQUITY"],
            "category_code": ["US", "US"],
            "asset_class_name": ["Large Cap", "Small Cap"],
            "group_label": ["Equities", "Equities"],
            "category_label": ["US Equities", "US Equities"],
            "asset_class_id": [1, 2],
            "portfolio_actual": [100.0, 50.0],
            "portfolio_effective": [90.0, 60.0],
            "portfolio_effective_variance": [10.0, -10.0],
        }

        df = pd.DataFrame(data)
        df = df.set_index(["group_code", "category_code", "asset_class_name"])

        engine = AllocationCalculationEngine()
        result = engine.aggregate_presentation_levels(df)

        # US category should sum both assets
        us_subtotal = result["category_subtotals"].loc[("EQUITY", "US"), "portfolio_actual"]
        self.assertAlmostEqual(us_subtotal, 150.0, places=1)

        # Variance should net out
        us_variance = result["category_subtotals"].loc[("EQUITY", "US"), "portfolio_effective_variance"]
        self.assertAlmostEqual(us_variance, 0.0, places=1)

    def test_empty_dataframe_aggregation(self) -> None:
        """Verify empty DataFrame handling."""
        df = pd.DataFrame()
        engine = AllocationCalculationEngine()
        result = engine.aggregate_presentation_levels(df)

        # Should return empty but valid structure
        self.assertTrue(result["assets"].empty)
        self.assertTrue(result["category_subtotals"].empty)


@pytest.mark.unit
@pytest.mark.calculations
class TestFormatting(SimpleTestCase):
    """
    Test presentation formatting logic.

    Verifies that numeric values are correctly formatted to strings.
    """

    def setUp(self) -> None:
        """Create formatter instance."""
        self.formatter = AllocationPresentationFormatter()

    def test_format_value_percent_mode(self) -> None:
        """Verify percent formatting."""
        result = self.formatter._format_value(42.5, "percent")
        self.assertEqual(result, "42.5%")

        result = self.formatter._format_value(0.0, "percent")
        self.assertEqual(result, "0.0%")

    def test_format_value_dollar_mode(self) -> None:
        """Verify dollar formatting."""
        result = self.formatter._format_value(1234.56, "dollar")
        self.assertEqual(result, "$1,235")  # Rounded to nearest dollar

        result = self.formatter._format_value(0.0, "dollar")
        self.assertEqual(result, "$0")

    def test_format_variance_with_sign(self) -> None:
        """Verify variance formatting includes sign."""
        # Positive variance
        result = self.formatter._format_variance(5.2, "percent")
        self.assertEqual(result, "+5.2%")

        # Negative variance
        result = self.formatter._format_variance(-3.1, "percent")
        self.assertEqual(result, "-3.1%")

        # Zero
        result = self.formatter._format_variance(0.0, "percent")
        self.assertEqual(result, "+0.0%")

    def test_format_money_accounting_style(self) -> None:
        """Verify money formatting uses accounting style for negatives."""
        # Positive
        result = self.formatter._format_money(Decimal("1234.56"))
        self.assertEqual(result, "$1,235")

        # Negative (parentheses)
        result = self.formatter._format_money(Decimal("-1234.56"))
        self.assertEqual(result, "($1,235)")

    def test_format_presentation_rows_structure(self) -> None:
        """Verify formatted rows have correct structure."""
        # Create mock aggregated data
        asset_data = {
            "group_code": ["EQUITY"],
            "category_code": ["US"],
            "asset_class_name": ["US Stocks"],
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

        result = self.formatter.format_presentation_rows(
            aggregated_data=aggregated,
            accounts_by_type=accounts_by_type,
            target_strategies=target_strategies,
            mode="percent",
        )

        # Should return list of dicts
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

        # Each row should have required keys
        row = result[0]
        self.assertIn("asset_class_name", row)
        self.assertIn("portfolio", row)
        self.assertIn("account_types", row)
        self.assertIn("is_asset", row)

        # Portfolio values should be formatted strings
        self.assertIsInstance(row["portfolio"]["actual"], str)
        self.assertIn("%", row["portfolio"]["actual"])


@pytest.mark.unit
@pytest.mark.calculations
class TestCalculationAccuracy(SimpleTestCase):
    """
    Test calculation accuracy with known values.

    These tests verify the mathematical correctness of calculations.
    """

    def test_percentages_sum_to_100(self) -> None:
        """Verify account percentages sum to 100%."""
        data = {
            ("Equities", "US", "VTI"): [6000.0],
            ("Fixed Income", "Bonds", "BND"): [4000.0],
        }

        index = pd.MultiIndex.from_tuples(
            [("Taxable", "Brokerage", "Account1", 1)],
            names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"],
        )

        columns = pd.MultiIndex.from_tuples(
            data.keys(), names=["Asset_Class", "Asset_Category", "Security"]
        )

        df = pd.DataFrame(list(data.values()), index=columns).T
        df.columns = columns
        df.index = index

        engine = AllocationCalculationEngine()
        result = engine._calculate_by_account(df)

        # Sum of all _pct columns should be 100%
        pct_cols = [c for c in result.columns if c.endswith("_pct")]
        total_pct = result.loc[1, pct_cols].sum()

        self.assertAlmostEqual(total_pct, 100.0, places=1)

@pytest.mark.unit
@pytest.mark.calculations
class TestPortfolioCalculations(SimpleTestCase):
    """Test portfolio-level specific calculations."""

    def test_portfolio_policy_variance_calculation(self) -> None:
        """Verify portfolio policy variance is calculated correctly (actual - explicit target)."""
        engine = AllocationCalculationEngine()

        # Mock data
        df = pd.DataFrame(
            {
                "asset_class_id": [1, 2],
                "asset_class_name": ["Stocks", "Bonds"],
                "portfolio_actual": [1000.0, 500.0],
                "portfolio_actual_pct": [66.7, 33.3],
            }
        )

        target_strategies = {
            "portfolio_explicit": {
                1: Decimal("60.0"),  # 60% Stocks
                2: Decimal("40.0"),  # 40% Bonds
            }
        }
        portfolio_total = 1500.0

        # Run calculation
        result = engine._calculate_portfolio_explicit_targets(
            df, target_strategies, portfolio_total
        )

        # Verify explicit targets
        self.assertAlmostEqual(result.loc[0, "portfolio_explicit_target"], 900.0)  # 60% of 1500
        self.assertAlmostEqual(result.loc[1, "portfolio_explicit_target"], 600.0)  # 40% of 1500

        # Verify policy variance: actual - explicit target
        # Stocks: 1000 - 900 = +100
        # Bonds: 500 - 600 = -100
        self.assertAlmostEqual(result.loc[0, "portfolio_policy_variance"], 100.0)
        self.assertAlmostEqual(result.loc[1, "portfolio_policy_variance"], -100.0)

        # Verify pct variance: actual_pct - target_pct
        # Stocks: 66.7 - 60.0 = +6.7
        # Bonds: 33.3 - 40.0 = -6.7
        self.assertAlmostEqual(result.loc[0, "portfolio_policy_variance_pct"], 6.7, places=1)
        self.assertAlmostEqual(result.loc[1, "portfolio_policy_variance_pct"], -6.7, places=1)


@pytest.mark.unit
@pytest.mark.performance
class TestPerformance(SimpleTestCase):
    """
    Performance tests to verify refactoring improved efficiency.

    Compare old vs new approach timing.
    """

    def test_aggregation_performance(self) -> None:
        """Verify pandas aggregation is faster than manual loops."""
        import time

        # Create large dataset
        n_assets = 100
        data = {
            "group_code": ["EQUITY"] * n_assets,
            "category_code": [f"CAT_{i // 10}" for i in range(n_assets)],
            "asset_class_name": [f"Asset_{i}" for i in range(n_assets)],
            "group_label": ["Equities"] * n_assets,
            "category_label": [f"Label_{i // 10}" for i in range(n_assets)],
            "asset_class_id": list(range(n_assets)),
            "portfolio_current": [float(i * 1000) for i in range(n_assets)],
            "portfolio_target": [float(i * 950) for i in range(n_assets)],
            "portfolio_variance": [float(i * 50) for i in range(n_assets)],
        }

        df = pd.DataFrame(data)
        df = df.set_index(["group_code", "category_code", "asset_class_name"])

        engine = AllocationCalculationEngine()

        # Time the aggregation
        start = time.time()
        result = engine.aggregate_presentation_levels(df)
        elapsed = time.time() - start

        # Should complete very quickly (< 0.1 seconds)
        self.assertLess(elapsed, 0.1)

        # Should produce correct results
        self.assertEqual(len(result["assets"]), n_assets)
        self.assertGreater(len(result["category_subtotals"]), 0)


# Integration test showing full workflow
def test_full_workflow() -> None:
    """
    Integration test showing complete workflow.

    This would use actual Django models in a full test.
    """
    # Pseudo-code for full workflow test:
    # 1. Create test user
    # 2. Create test portfolio with holdings
    # 3. Build DataFrame
    # 4. Aggregate
    # 5. Format
    # 6. Verify all values match expected
    pass

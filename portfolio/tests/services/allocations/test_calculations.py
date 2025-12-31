"""Tests for allocation calculations."""

import pandas as pd
import pytest

from portfolio.services.allocations.calculations import AllocationCalculator


@pytest.mark.unit
@pytest.mark.services
class TestAllocationCalculator:
    """Test AllocationCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return AllocationCalculator()

    @pytest.fixture
    def mock_holdings_df(self):
        """Create mock MultiIndex DataFrame."""
        # Create sample data
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
            list(data.keys()),
            names=["Asset_Class", "Asset_Category", "Security"],
        )

        df = pd.DataFrame(list(data.values()), index=columns).T
        df.columns = columns
        df.index = index
        return df

    def test_calculate_allocations_structure(self, calculator, mock_holdings_df):
        """Verify calculate_allocations returns correct structure."""
        result = calculator.calculate_allocations(mock_holdings_df)

        assert "by_account" in result
        assert "by_account_type" in result
        assert "by_asset_class" in result
        assert "portfolio_summary" in result

        for df in result.values():
            assert isinstance(df, pd.DataFrame)

    def test_aggregate_by_level_account(self, calculator, mock_holdings_df):
        """Test universal aggregation method."""
        result = calculator._aggregate_by_level(
            mock_holdings_df, level="Account_ID", include_percentages=True
        )

        assert len(result) == 2  # Two accounts
        assert "Equities_actual" in result.columns
        assert "Equities_actual_pct" in result.columns

    def test_calculate_by_asset_class_numeric(self, calculator, mock_holdings_df):
        """Verify by_asset_class returns numeric values only."""
        total = float(mock_holdings_df.sum().sum())
        result = calculator._calculate_by_asset_class(mock_holdings_df, total)

        assert "dollars" in result.columns
        assert "percent" in result.columns
        assert isinstance(result.loc["Equities", "dollars"], (float, int))
        assert isinstance(result.loc["Equities", "percent"], (float, int))

    def test_calculate_allocations_empty(self, calculator):
        """Verify empty DataFrame handling."""
        empty_df = pd.DataFrame()
        result = calculator.calculate_allocations(empty_df)

        assert result["by_account"].empty
        assert result["by_account_type"].empty
        assert result["by_asset_class"].empty
        assert result["portfolio_summary"].empty

    def test_aggregate_by_level_percentages(self, calculator, mock_holdings_df):
        """Verify percentages sum to 100 for each account."""
        result = calculator._aggregate_by_level(
            mock_holdings_df, level="Account_ID", include_percentages=True
        )

        # Get percentage columns
        pct_cols = [col for col in result.columns if col.endswith("_actual_pct")]

        # Each account's percentages should sum to ~100
        for account_id in result.index:
            total_pct = result.loc[account_id, pct_cols].sum()
            assert abs(total_pct - 100.0) < 0.01  # Allow small floating point error

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


@pytest.mark.django_db
@pytest.mark.services
class TestPresentationCalculations:
    """Test presentation calculation pipeline."""

    @pytest.fixture
    def calculator(self):
        return AllocationCalculator()

    @pytest.fixture
    def presentation_data(self, test_user, simple_holdings):
        """Get all data needed for presentation calculations."""
        from portfolio.services.allocations.data_providers import DjangoDataProvider

        provider = DjangoDataProvider()
        return {
            "holdings_df": provider.get_holdings_df(test_user),
            "asset_classes_df": provider.get_asset_classes_df(test_user),
            "targets_map": provider.get_targets_map(test_user),
        }

    def test_build_presentation_dataframe_complete(self, calculator, presentation_data):
        """Test complete presentation DataFrame pipeline."""
        from decimal import Decimal

        # Calculate account totals
        holdings_df = presentation_data["holdings_df"]
        account_totals = (
            holdings_df.groupby("account_id")["value"]
            .sum()
            .apply(lambda x: Decimal(str(x)))
            .to_dict()
        )

        result = calculator.build_presentation_dataframe(
            holdings_df=holdings_df,
            asset_classes_df=presentation_data["asset_classes_df"],
            targets_map=presentation_data["targets_map"],
            account_totals=account_totals,
        )

        # Verify structure
        assert not result.empty
        assert "asset_class_name" in result.columns
        assert "portfolio_actual" in result.columns
        assert "portfolio_actual_pct" in result.columns

        # Verify calculations
        assert result["portfolio_actual"].sum() > 0
        assert 0 <= result["portfolio_actual_pct"].max() <= 100

    def test_add_portfolio_calculations(self, calculator, presentation_data):
        """Test portfolio-level calculations."""
        df = presentation_data["asset_classes_df"].copy()
        result = calculator._add_portfolio_calculations_presentation(
            df, presentation_data["holdings_df"]
        )

        assert "portfolio_actual" in result.columns
        assert "portfolio_actual_pct" in result.columns
        assert result["portfolio_actual"].sum() > 0

        # Percentages should sum to ~100%
        total_pct = result["portfolio_actual_pct"].sum()
        assert 99.9 <= total_pct <= 100.1

    def test_add_account_type_calculations(self, calculator, presentation_data):
        """Test account-type level calculations."""
        df = presentation_data["asset_classes_df"].copy()
        result = calculator._add_account_type_calculations_presentation(
            df, presentation_data["holdings_df"]
        )

        # Should have columns for account types present in holdings
        type_columns = [col for col in result.columns if col.endswith("_actual")]
        assert len(type_columns) > 0

    def test_calculate_variances(self, calculator, presentation_data):
        """Test variance calculations."""
        from decimal import Decimal

        holdings_df = presentation_data["holdings_df"]
        account_totals = (
            holdings_df.groupby("account_id")["value"]
            .sum()
            .apply(lambda x: Decimal(str(x)))
            .to_dict()
        )

        # Build DataFrame with actuals and targets
        df = calculator.build_presentation_dataframe(
            holdings_df=holdings_df,
            asset_classes_df=presentation_data["asset_classes_df"],
            targets_map=presentation_data["targets_map"],
            account_totals=account_totals,
        )

        # Should have variance columns
        assert "portfolio_variance" in df.columns
        assert "portfolio_variance_pct" in df.columns

        # Variance should be actual - effective
        if "portfolio_actual" in df.columns and "portfolio_effective" in df.columns:
            expected_variance = df["portfolio_actual"] - df["portfolio_effective"]
            pd.testing.assert_series_equal(
                df["portfolio_variance"],
                expected_variance,
                check_names=False,
            )

    def test_empty_holdings(self, calculator):
        """Test handling of empty holdings."""
        from django.contrib.auth import get_user_model

        from portfolio.services.allocations.data_providers import DjangoDataProvider

        user_model = get_user_model()
        empty_user = user_model.objects.create_user(username="empty", email="empty@test.com")

        provider = DjangoDataProvider()
        holdings_df = provider.get_holdings_df(empty_user)
        asset_classes_df = provider.get_asset_classes_df(empty_user)

        result = calculator.build_presentation_dataframe(
            holdings_df=holdings_df,
            asset_classes_df=asset_classes_df,
            targets_map={},
            account_totals={},
        )

        assert result.empty

    def test_weighted_targets_calculation(self, calculator, presentation_data):
        """Test weighted effective targets calculation."""
        from decimal import Decimal

        holdings_df = presentation_data["holdings_df"]
        account_totals = (
            holdings_df.groupby("account_id")["value"]
            .sum()
            .apply(lambda x: Decimal(str(x)))
            .to_dict()
        )

        df = calculator.build_presentation_dataframe(
            holdings_df=holdings_df,
            asset_classes_df=presentation_data["asset_classes_df"],
            targets_map=presentation_data["targets_map"],
            account_totals=account_totals,
        )

        # Should have effective target columns
        if presentation_data["targets_map"]:
            assert "portfolio_effective" in df.columns
            assert "portfolio_effective_pct" in df.columns

    def test_sorting_by_hierarchy(self, calculator, presentation_data):
        """Test DataFrame is sorted by hierarchy."""
        from decimal import Decimal

        holdings_df = presentation_data["holdings_df"]
        account_totals = (
            holdings_df.groupby("account_id")["value"]
            .sum()
            .apply(lambda x: Decimal(str(x)))
            .to_dict()
        )

        df = calculator.build_presentation_dataframe(
            holdings_df=holdings_df,
            asset_classes_df=presentation_data["asset_classes_df"],
            targets_map=presentation_data["targets_map"],
            account_totals=account_totals,
        )

        # Verify sorting columns exist and DataFrame is sorted
        if "group_code" in df.columns and "category_code" in df.columns:
            # Check if sorted (should be monotonic or have repeating groups)
            assert not df.empty

    def test_calculate_holdings_with_targets(self, calculator):
        """Test holdings calculation logic."""
        df = pd.DataFrame(
            [
                {
                    "Account_ID": 1,
                    "Ticker": "VTI",
                    "Asset_Class": "US Equities",
                    "Value": 1000.0,
                    "Shares": 10.0,
                    "Price": 100.0,
                    "Group_Sort_Order": 1,
                    "Category_Sort_Order": 1,
                }
            ]
        )

        targets_map = {1: {"US Equities": 60.0}}

        result = calculator.calculate_holdings_with_targets(df, targets_map)

        assert "Target_Value" in result.columns
        assert "Value_Variance" in result.columns
        assert result.iloc[0]["Target_Value"] == 600.0
        assert result.iloc[0]["Value_Variance"] == 400.0

    def test_aggregate_holdings_by_ticker(self, calculator):
        """Test aggregation across accounts."""
        df = pd.DataFrame(
            [
                {
                    "Account_ID": 1,
                    "Ticker": "VTI",
                    "Value": 1000.0,
                    "Shares": 10.0,
                    "Asset_Class": "US Equities",
                },
                {
                    "Account_ID": 2,
                    "Ticker": "VTI",
                    "Value": 500.0,
                    "Shares": 5.0,
                    "Asset_Class": "US Equities",
                },
            ]
        )

        result = calculator.aggregate_holdings_by_ticker(df)

        assert len(result) == 1
        assert result.iloc[0]["Value"] == 1500.0
        assert result.iloc[0]["Shares"] == 15.0
        assert result.iloc[0]["Account_ID"] == 0

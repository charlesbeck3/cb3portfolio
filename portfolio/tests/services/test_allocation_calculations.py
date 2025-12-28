"""
Tests for allocation calculation engine.

Tests: portfolio/services/allocation_calculations.py
"""

from decimal import Decimal
from typing import Any

from django.utils import timezone

import pandas as pd
import pytest

from portfolio.models import Account, Holding, SecurityPrice
from portfolio.services.allocation_calculations import AllocationCalculationEngine


@pytest.mark.services
@pytest.mark.calculations
class TestAllocationCalculationEngine:
    """Tests for the core calculation engine using pandas."""

    @pytest.fixture
    def engine(self) -> AllocationCalculationEngine:
        return AllocationCalculationEngine()

    @pytest.fixture
    def mock_holdings_df(self) -> pd.DataFrame:
        """Create mock holdings DataFrame for pure calculation tests."""
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
        return df

    def test_calculate_by_asset_class_returns_numeric_only(
        self, engine: AllocationCalculationEngine, mock_holdings_df: pd.DataFrame
    ) -> None:
        """Verify by_asset_class returns only numeric values."""
        result = engine._calculate_by_asset_class(mock_holdings_df, 20000.0)
        assert "dollars" in result.columns
        assert "percent" in result.columns
        assert isinstance(result.loc["Equities", "dollars"], (float, int))
        assert isinstance(result.loc["Equities", "percent"], (float, int))

    def test_calculate_allocations_structure(
        self, engine: AllocationCalculationEngine, mock_holdings_df: pd.DataFrame
    ) -> None:
        """Verify calculate_allocations returns correct structure."""
        result = engine.calculate_allocations(mock_holdings_df)
        assert "by_account" in result
        assert "by_account_type" in result
        assert "by_asset_class" in result
        assert "portfolio_summary" in result
        for df in result.values():
            assert isinstance(df, pd.DataFrame)

    def test_by_account_numeric_values(
        self, engine: AllocationCalculationEngine, mock_holdings_df: pd.DataFrame
    ) -> None:
        """Verify by_account returns correct numeric values."""
        result = engine._calculate_by_account(mock_holdings_df)
        assert pytest.approx(result.loc[1, "Equities_actual_pct"]) == 50.0
        assert pytest.approx(result.loc[1, "Equities_actual"]) == 5000.0

    def test_aggregate_presentation_levels(self, engine: AllocationCalculationEngine) -> None:
        """Verify aggregation returns all expected levels."""
        data = {
            "group_code": ["EQUITY", "EQUITY", "FIXED"],
            "category_code": ["US", "INTL", "BONDS"],
            "asset_class_name": ["US Equities", "Intl Stocks", "Bonds"],
            "group_label": ["Equities", "Equities", "Fixed Income"],
            "category_label": ["US Equities", "Intl Equities", "Fixed Income Bonds"],
            "asset_class_id": [1, 2, 3],
            "portfolio_actual": [100.0, 50.0, 150.0],
            "portfolio_effective": [120.0, 60.0, 120.0],
            "portfolio_effective_variance": [-20.0, -10.0, 30.0],
        }
        df = pd.DataFrame(data).set_index(["group_code", "category_code", "asset_class_name"])
        result = engine.aggregate_presentation_levels(df)

        assert "assets" in result
        assert "category_subtotals" in result
        assert pytest.approx(result["group_totals"].loc["EQUITY", "portfolio_actual"]) == 150.0
        assert pytest.approx(result["grand_total"].iloc[0]["portfolio_actual"]) == 300.0

    @pytest.mark.django_db
    def test_get_account_totals(
        self, engine: AllocationCalculationEngine, test_user: Any, base_system_data: Any
    ) -> None:
        """Test get_account_totals from database integration.

        Migrated from: AllocationCalculationEngineTotalsTests.test_get_account_totals_simple
        """
        from portfolio.models import Portfolio as PortfolioModel

        system = base_system_data
        portfolio = PortfolioModel.objects.create(user=test_user, name="Test Portfolio")
        account = Account.objects.create(
            user=test_user,
            name="Test Account",
            portfolio=portfolio,
            account_type=system.type_taxable,
            institution=system.institution,
        )

        Holding.objects.create(account=account, security=system.vti, shares=Decimal("10"))
        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100.00"),
            price_datetime=timezone.now(),
            source="manual",
        )

        totals = engine.get_account_totals(test_user)
        assert totals[account.id] == Decimal("1000.00")

    @pytest.mark.performance
    def test_performance_with_large_dataset(
        self, engine: AllocationCalculationEngine, large_portfolio_benchmark: dict[str, Any]
    ) -> None:
        """Verify performance of calculation pipeline."""
        import time

        user = large_portfolio_benchmark["user"]

        start = time.time()
        df = engine.build_presentation_dataframe(user)
        result = engine.aggregate_presentation_levels(df)
        elapsed = time.time() - start

        assert elapsed < 1.0
        assert (
            abs(
                result["grand_total"].iloc[0]["portfolio_actual"]
                - float(large_portfolio_benchmark["total_value"])
            )
            < 1.0
        )

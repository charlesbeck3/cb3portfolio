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
        """Verify aggregation returns all expected levels in single DataFrame."""
        data = {
            "group_code": ["EQUITY", "EQUITY", "EQUITY", "FIXED"],
            "category_code": ["US", "US", "INTL", "BONDS"],
            "asset_class_name": ["US Large Cap", "US Small Cap", "Intl Stocks", "Bonds"],
            "group_label": ["Equities", "Equities", "Equities", "Fixed Income"],
            "category_label": ["US Equities", "US Equities", "Intl Equities", "Fixed Income Bonds"],
            "asset_class_id": [1, 2, 3, 4],
            "portfolio_actual": [50.0, 50.0, 50.0, 150.0],
            "portfolio_effective": [60.0, 60.0, 60.0, 120.0],
            "portfolio_actual_pct": [5.0, 5.0, 5.0, 15.0],
            "portfolio_effective_pct": [6.0, 6.0, 6.0, 12.0],
        }
        df = pd.DataFrame(data).set_index(["group_code", "category_code", "asset_class_name"])
        result = engine.aggregate_presentation_levels(df)

        assert isinstance(result, pd.DataFrame)
        assert "row_type" in result.columns

        # Check all levels exist
        row_types = result["row_type"].unique()
        assert "asset" in row_types
        assert "subtotal" in row_types
        assert "group_total" in row_types
        assert "grand_total" in row_types

        # Verify values
        # Grand total
        grand_row = result[result["row_type"] == "grand_total"].iloc[0]
        assert pytest.approx(grand_row["portfolio_actual"]) == 300.0

        # Group total
        group_row = result[
            (result["row_type"] == "group_total") & (result["group_code"] == "EQUITY")
        ].iloc[0]
        assert pytest.approx(group_row["portfolio_actual"]) == 150.0

        # Verify variances are computed (now that engine does it)
        # 50 - 60 = -10 (US Large Cap)
        # Find asset row for US Large Cap. Need to handle potential re-indexing.
        # Asset rows have row_type="asset"
        asset_row = result[(result["row_type"] == "asset") & (result["asset_class_id"] == 1)].iloc[
            0
        ]
        assert pytest.approx(asset_row["portfolio_effective_variance"]) == -10.0

    def test_aggregate_presentation_levels_includes_variances(
        self, engine: AllocationCalculationEngine
    ) -> None:
        """Verify all variance columns are calculated by engine."""
        data = {
            "group_code": ["EQUITY", "EQUITY"],
            "category_code": ["US", "INTL"],
            "asset_class_name": ["US Equities", "Intl Stocks"],
            "portfolio_actual": [100.0, 50.0],
            "portfolio_actual_pct": [10.0, 5.0],
            "portfolio_effective": [120.0, 60.0],
            "portfolio_effective_pct": [12.0, 6.0],
            "asset_class_id": [1, 2],
            # Account columns
            "acc_1_actual": [100.0, 50.0],
            "acc_1_effective": [120.0, 60.0],
            "acc_1_actual_pct": [10.0, 5.0],
            "acc_1_effective_pct": [12.0, 6.0],
        }
        df = pd.DataFrame(data).set_index(["group_code", "category_code", "asset_class_name"])
        result = engine.aggregate_presentation_levels(df)

        # Check portfolio variances exist
        assert "portfolio_effective_variance" in result.columns
        assert "portfolio_effective_variance_pct" in result.columns

        # Check values for asset row
        asset_row = result[(result["row_type"] == "asset") & (result["asset_class_id"] == 1)].iloc[
            0
        ]
        assert pytest.approx(asset_row["portfolio_effective_variance"]) == -20.0
        assert pytest.approx(asset_row["portfolio_effective_variance_pct"]) == -2.0

        # Check account variances exist
        assert "acc_1_variance" in result.columns
        assert "acc_1_variance_pct" in result.columns
        assert pytest.approx(asset_row["acc_1_variance"]) == -20.0
        assert pytest.approx(asset_row["acc_1_variance_pct"]) == -2.0

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

        grand_total_row = result[result["row_type"] == "grand_total"].iloc[0]
        assert (
            abs(
                grand_total_row["portfolio_actual"]
                - float(large_portfolio_benchmark["total_value"])
            )
            < 1.0
        )

    @pytest.mark.django_db
    def test_calculate_holdings_with_targets_sorting(
        self, engine: AllocationCalculationEngine, base_system_data: Any, test_user: Any
    ) -> None:
        """Verify holdings are sorted by group/category order then target value."""
        from portfolio.models import (
            Account,
            AssetClass,
            AssetClassCategory,
            Holding,
            Portfolio,
            Security,
            SecurityPrice,
        )

        system = base_system_data
        portfolio = Portfolio.objects.create(user=test_user, name="Sort Test")
        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            account_type=system.type_taxable,
            name="Test Account",
            institution=system.institution,
        )

        # Setup hierarchy: Group 1 (Sort 10) -> Cat A (Sort 1) -> Asset 1
        #                  Group 1 (Sort 10) -> Cat B (Sort 2) -> Asset 2
        #                  Group 2 (Sort 20) -> Cat C (Sort 1) -> Asset 3

        # Create groups
        group1 = AssetClassCategory.objects.create(code="GRP1", label="Group 1", sort_order=10)
        group2 = AssetClassCategory.objects.create(code="GRP2", label="Group 2", sort_order=20)

        # Create categories
        cat_a = AssetClassCategory.objects.create(
            code="CATA", label="Cat A", parent=group1, sort_order=1
        )
        cat_b = AssetClassCategory.objects.create(
            code="CATB", label="Cat B", parent=group1, sort_order=2
        )
        cat_c = AssetClassCategory.objects.create(
            code="CATC", label="Cat C", parent=group2, sort_order=1
        )

        # Create assets
        asset1 = AssetClass.objects.create(name="Asset 1", category=cat_a)
        asset2 = AssetClass.objects.create(name="Asset 2", category=cat_b)
        asset3 = AssetClass.objects.create(name="Asset 3", category=cat_c)

        # Create securities
        sec1 = Security.objects.create(ticker="TIC1", asset_class=asset1)
        sec2 = Security.objects.create(ticker="TIC2", asset_class=asset2)
        sec3 = Security.objects.create(ticker="TIC3", asset_class=asset3)
        # Add another security in Cat A with lower value to test value sorting
        sec1_small = Security.objects.create(ticker="TIC1S", asset_class=asset1)

        # Create holdings
        # Group 2 (should be last)
        Holding.objects.create(account=account, security=sec3, shares=Decimal("10"))
        SecurityPrice.objects.create(
            security=sec3,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="manual",
        )

        # Group 1, Cat B (should be 2nd)
        Holding.objects.create(account=account, security=sec2, shares=Decimal("10"))
        SecurityPrice.objects.create(
            security=sec2,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="manual",
        )

        # Group 1, Cat A, Large (should be 1st)
        Holding.objects.create(account=account, security=sec1, shares=Decimal("20"))
        SecurityPrice.objects.create(
            security=sec1,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="manual",
        )

        # Group 1, Cat A, Small (should be 2nd in Cat A)
        Holding.objects.create(account=account, security=sec1_small, shares=Decimal("5"))
        SecurityPrice.objects.create(
            security=sec1_small,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="manual",
        )

        # Run calculation
        df = engine.calculate_holdings_with_targets(test_user, account.id)

        # Verify sorting
        assert not df.empty
        tickers = df["Ticker"].tolist()

        # Expected order:
        # 1. TIC1 (Group 1, Cat A, Value 2000)
        # 2. TIC1S (Group 1, Cat A, Value 500)
        # 3. TIC2 (Group 1, Cat B, Value 1000)
        # 4. TIC3 (Group 2, Cat C, Value 1000)

        assert tickers == ["TIC1", "TIC1S", "TIC2", "TIC3"]

        # Double check implicit sort columns
        assert df.iloc[0]["Group_Sort_Order"] == 10
        assert df.iloc[2]["Group_Sort_Order"] == 10
        assert df.iloc[3]["Group_Sort_Order"] == 20


@pytest.mark.services
@pytest.mark.presentation
class TestAllocationPresentation:
    """Test the formatting of calculation results for display (migrated from Formatter)."""

    @pytest.fixture
    def engine(self) -> AllocationCalculationEngine:
        return AllocationCalculationEngine()

    def test_format_presentation_rows_structure(self, engine: AllocationCalculationEngine) -> None:
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

        accounts_by_type: dict[int, list[dict[str, Any]]] = {}
        target_strategies: dict[str, Any] = {"at_strategy_map": {}, "acc_strategy_map": {}}

        # Use private method _format_presentation_rows
        result = engine._format_presentation_rows(
            df=df_assets,
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
        self, engine: AllocationCalculationEngine
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

        # Prepare DF for formatter
        df["row_type"] = "asset"
        df["group_code"] = "G"
        df["category_code"] = "C"
        df["group_label"] = "G"
        df["category_label"] = "C"
        df["asset_class_id"] = [1, 2]

        # 3. Format
        rows = engine._format_presentation_rows(
            df=df,
            accounts_by_type={},
            target_strategies={},
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

    def test_formatter_exposes_policy_variance_row_build(
        self, engine: AllocationCalculationEngine
    ) -> None:
        """
        Directly test the _build_row_dict_from_formatted_data method.
        """
        row_data = {
            "asset_class_name": "Test Asset",
            "portfolio_actual": 100.0,
            "portfolio_explicit_target": 80.0,
            "portfolio_policy_variance": 20.0,
            "portfolio_effective_variance": 10.0,
        }

        result = engine._build_row_dict_from_formatted_data(
            row=row_data,
            accounts_by_type={},
            target_strategies={},
        )

        # Verify the dict structure
        assert result["portfolio"]["policy_variance"] == 20.0
        assert result["portfolio"]["effective_variance"] == 10.0


@pytest.mark.integration
@pytest.mark.services
class TestAllocationCalculationEngineTargetContext:
    """Test build_target_allocation_context method."""

    def test_build_target_allocation_context_structure(self, test_user, base_system_data):
        """Test that build_target_allocation_context returns expected structure."""
        engine = AllocationCalculationEngine()
        context = engine.build_target_allocation_context(user=test_user)

        assert "allocation_rows_percent" in context
        assert "allocation_rows_money" in context
        assert "strategies" in context
        assert "portfolio_total_value" in context

        # Verify strategies query
        assert list(context["strategies"]) == []

    def test_build_target_allocation_context_with_strategies(self, test_user):
        """Test that strategies are included in context."""
        from portfolio.models import AllocationStrategy

        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        engine = AllocationCalculationEngine()
        context = engine.build_target_allocation_context(user=test_user)

        assert strategy in context["strategies"]

    def test_build_target_allocation_context_with_portfolio_data(self, test_user, base_system_data):
        """Test context includes portfolio total when data exists."""
        from decimal import Decimal

        from portfolio.models import Account, Holding, Portfolio

        # Create portfolio with holdings
        portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")
        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Test Account",
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )
        # Use existing security from fixture
        security = base_system_data.vti

        Holding.objects.create(
            account=account,
            security=security,
            shares=Decimal("100.00"),
        )
        # Mock price to ensure value > 0
        from portfolio.models import SecurityPrice

        SecurityPrice.objects.update_or_create(
            security=security,
            defaults={
                "price": Decimal("100.00"),
                "price_datetime": timezone.now(),
            },
        )

        engine = AllocationCalculationEngine()
        context = engine.build_target_allocation_context(user=test_user)

        # Should have a non-zero portfolio total
        assert context["portfolio_total_value"] >= Decimal("0.00")
        assert isinstance(context["portfolio_total_value"], Decimal)


@pytest.mark.services
class TestDataFrameMetadata:
    """Test DataFrame-based metadata methods."""

    @pytest.fixture
    def engine(self) -> AllocationCalculationEngine:
        return AllocationCalculationEngine()

    @pytest.fixture
    def test_portfolio(self, test_user, base_system_data):
        """Standard test portfolio with data."""
        from decimal import Decimal

        from portfolio.models import (
            Account,
            AllocationStrategy,
            Portfolio,
            TargetAllocation,
        )

        portfolio = Portfolio.objects.create(user=test_user, name="Metadata Test")

        # Create Account
        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Test Account",
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        # Create Strategy & Target
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        # Create Asset Class (using category from system data if available, or just mocking it)
        # Assuming base_system_data has categories. Let's look at the error again.
        # It seems safer to create a fresh asset class.
        from portfolio.models import AssetClass, AssetClassCategory

        # Ensure we have a category
        if hasattr(base_system_data, "us_large_cap"):
            cat = base_system_data.us_large_cap
        else:
            cat = AssetClassCategory.objects.first() or AssetClassCategory.objects.create(
                code="TEST", label="Test"
            )

        ac = AssetClass.objects.create(name="US Stock", category=cat)

        TargetAllocation.objects.create(
            strategy=strategy, asset_class=ac, target_percent=Decimal("60.00")
        )

        return {"user": test_user, "portfolio": portfolio, "account": account}

    @pytest.mark.django_db
    def test_get_asset_class_metadata_df(self, engine, test_portfolio):
        """Test asset class metadata as DataFrame."""
        user = test_portfolio["user"]
        df = engine._get_asset_class_metadata_df(user)

        assert not df.empty
        assert "asset_class_id" in df.columns
        assert "group_code" in df.columns
        assert "is_cash" in df.columns
        assert "asset_class_name" in df.columns

        # Verify content
        assert "US Stock" in df["asset_class_name"].values

    @pytest.mark.django_db
    def test_get_accounts_metadata_df(self, engine, test_portfolio):
        """Test accounts metadata as DataFrame."""
        user = test_portfolio["user"]
        df = engine._get_accounts_metadata_df(user)

        assert not df.empty
        assert "account_id" in df.columns
        assert "tax_treatment" in df.columns
        assert "account_name" in df.columns

        # Verify content
        assert test_portfolio["account"].id in df["account_id"].values

    @pytest.mark.django_db
    def test_get_targets_df(self, engine, test_portfolio):
        """Test targets as DataFrame."""
        user = test_portfolio["user"]
        df = engine._get_targets_df(user)

        assert not df.empty
        assert "target_percent" in df.columns
        assert "strategy_id" in df.columns

        # Verify content
        from decimal import Decimal

        # Check for float or Decimal depending on what DataFrame conversion does
        values = df["target_percent"].values
        assert any(v == 60.00 for v in values) or any(v == Decimal("60.00") for v in values)

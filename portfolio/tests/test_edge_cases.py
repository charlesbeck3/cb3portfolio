from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

import pytest

from portfolio.models import Account, AllocationStrategy, Holding, TargetAllocation
from portfolio.tests.fixtures.mocks import MockMarketPrices

from .base import PortfolioTestMixin

User = get_user_model()

@pytest.mark.edge_cases
class TestEmptyPortfolio(TestCase, PortfolioTestMixin):
    """Test behavior when portfolio has no holdings."""

    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.client.force_login(self.user)

    def test_empty_portfolio_allocations(self) -> None:
        """Empty portfolio should return zeros, not crash."""
        from portfolio.services.allocation_calculations import AllocationCalculationEngine
        engine = AllocationCalculationEngine()
        df = engine.build_presentation_dataframe(user=self.user)

        # If empty, df should be empty
        self.assertTrue(df.empty)

        # Check aggregation on empty df
        aggregated = engine.aggregate_presentation_levels(df)
        self.assertTrue(aggregated["grand_total"].empty)

    def test_empty_portfolio_dashboard(self) -> None:
        """Dashboard should render cleanly with no holdings."""
        from django.urls import reverse
        with MockMarketPrices({}):
            response = self.client.get(reverse("portfolio:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard", response.content.decode())


@pytest.mark.edge_cases
class TestDecimalPrecision(TestCase, PortfolioTestMixin):
    """Test handling of decimal precision edge cases."""

    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)

    def test_allocations_sum_to_99_99(self) -> None:
        """Allocations summing to 99.99% should be handled by cash remainder."""
        strategy = AllocationStrategy.objects.create(user=self.user, name="99.99 Strategy")
        # Asset classes
        ac_us = self.asset_class_us_equities
        TargetAllocation.objects.create(strategy=strategy, asset_class=ac_us, target_percent=Decimal("99.99"))

        # Cash should be 0.01%
        # AllocationStrategy model now has logic to handle cash remainder if used via save_allocations
        strategy.save_allocations({ac_us.id: Decimal("99.99")})

        cash_alloc = strategy.target_allocations.get(asset_class=self.asset_class_cash)
        self.assertEqual(cash_alloc.target_percent, Decimal("0.01"))


@pytest.mark.edge_cases
class TestLargeValues(TestCase, PortfolioTestMixin):
    """Test handling of very large portfolio values."""

    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)

        self.account = Account.objects.create(
            user=self.user,
            name="Whale Account",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )

    def test_billion_dollar_portfolio(self) -> None:
        """Calculations should work for $1B+ portfolios."""
        # 10,000,000 shares @ $100 = $1B
        Holding.objects.create(
            account=self.account,
            security=self.vti,
            shares=Decimal("10000000"),
            current_price=Decimal("100")
        )

        from portfolio.services.allocation_calculations import AllocationCalculationEngine
        engine = AllocationCalculationEngine()
        df = engine.build_presentation_dataframe(user=self.user)
        aggregated = engine.aggregate_presentation_levels(df)

        grand_total = aggregated["grand_total"]
        # Columns in grand_total include 'portfolio_actual'
        self.assertEqual(grand_total["portfolio_actual"].iloc[0], 1000000000.0)


@pytest.mark.edge_cases
class TestAccountWithNoHoldings(TestCase, PortfolioTestMixin):
    """Account exists but has zero holdings - should appear with $0."""

    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.account = Account.objects.create(
            user=self.user,
            name="Empty Account",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )

    def test_account_valuation(self) -> None:
        self.assertEqual(self.account.total_value(), Decimal("0.00"))


@pytest.mark.edge_cases
class TestPartialAllocations(TestCase, PortfolioTestMixin):
    """Allocations that don't sum to 100% - auto-allocate to cash."""

    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.strategy = AllocationStrategy.objects.create(user=self.user, name="Partial Strategy")

    def test_auto_fill_cash(self) -> None:
        # 80% to US Equities
        self.strategy.save_allocations({
            self.asset_class_us_equities.id: Decimal("80.00")
        })

        # Should have created a cash allocation of 20%
        cash_alloc = self.strategy.target_allocations.get(asset_class=self.asset_class_cash)
        self.assertEqual(cash_alloc.target_percent, Decimal("20.00"))


@pytest.mark.edge_cases
class TestMultipleAccountsSameType(TestCase, PortfolioTestMixin):
    """Type-level allocation applies to all accounts of that type."""

    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)

        # Create two taxable accounts
        self.acc1 = Account.objects.create(
            user=self.user, name="Taxable 1", portfolio=self.portfolio,
            account_type=self.type_taxable, institution=self.institution
        )
        self.acc2 = Account.objects.create(
            user=self.user, name="Taxable 2", portfolio=self.portfolio,
            account_type=self.type_taxable, institution=self.institution
        )

        # Create strategy
        self.strategy = AllocationStrategy.objects.create(user=self.user, name="Taxable Strategy")

        # Assign to TYPE
        from portfolio.models import AccountTypeStrategyAssignment
        AccountTypeStrategyAssignment.objects.create(
            user=self.user, account_type=self.type_taxable, allocation_strategy=self.strategy
        )

    def test_strategy_inheritance(self) -> None:
        # Both accounts should inherit the strategy
        self.assertEqual(self.acc1.get_effective_allocation_strategy(), self.strategy)
        self.assertEqual(self.acc2.get_effective_allocation_strategy(), self.strategy)


@pytest.mark.edge_cases
class TestZeroPriceSecurities(TestCase, PortfolioTestMixin):
    """Holdings with missing or zero prices."""

    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.account = Account.objects.create(
            user=self.user, name="Acc", portfolio=self.portfolio,
            account_type=self.type_taxable, institution=self.institution
        )

    def test_zero_price_valuation(self) -> None:
        # Holding with 0 price explicitly
        h = Holding.objects.create(
            account=self.account, security=self.vti, shares=100, current_price=Decimal("0.00")
        )
        self.assertEqual(h.market_value, Decimal("0.00"))

    def test_null_price_valuation(self) -> None:
        # Holding with noprice
        h = Holding.objects.create(
            account=self.account, security=self.vxus, shares=100, current_price=None
        )
        self.assertEqual(h.market_value, Decimal("0.00"))

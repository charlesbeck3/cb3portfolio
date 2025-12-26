from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import Account, AllocationStrategy, Holding, TargetAllocation

from .base import PortfolioTestMixin

User = get_user_model()

class TestEmptyPortfolio(TestCase, PortfolioTestMixin):
    """Test behavior when portfolio has no holdings."""

    def setUp(self) -> None:
        self.setup_portfolio_data()
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
        response = self.client.get(reverse("portfolio:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard", response.content.decode())


class TestDecimalPrecision(TestCase, PortfolioTestMixin):
    """Test handling of decimal precision edge cases."""

    def setUp(self) -> None:
        self.setup_portfolio_data()
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


class TestLargeValues(TestCase, PortfolioTestMixin):
    """Test handling of very large portfolio values."""

    def setUp(self) -> None:
        self.setup_portfolio_data()
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

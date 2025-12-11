from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.domain import Portfolio
from portfolio.models import Account, AssetClass, Holding, Security

from .base import PortfolioTestMixin

User = get_user_model()


class PortfolioAggregateTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")

        # Simple setup: two accounts with different mixes
        self.asset_us = AssetClass.objects.create(name="US Stocks", category=self.cat_us_eq)
        self.asset_bonds = AssetClass.objects.create(name="Bonds", category=self.cat_fi)

        self.account1 = Account.objects.create(
            user=self.user,
            name="Account 1",
            account_type=self.type_roth,
            institution=self.institution,
        )
        self.account2 = Account.objects.create(
            user=self.user,
            name="Account 2",
            account_type=self.type_taxable,
            institution=self.institution,
        )

        sec_stock = Security.objects.create(ticker="STK", name="Stock", asset_class=self.asset_us)
        sec_bond = Security.objects.create(ticker="BND", name="Bond", asset_class=self.asset_bonds)

        # Account 1: 600 stocks, 400 bonds
        Holding.objects.create(
            account=self.account1,
            security=sec_stock,
            shares=Decimal("6"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=self.account1,
            security=sec_bond,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

        # Account 2: 400 stocks only
        Holding.objects.create(
            account=self.account2,
            security=sec_stock,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

        self.portfolio = Portfolio(user_id=self.user.id, accounts=[self.account1, self.account2])

    def test_total_value_and_value_by_account_type(self) -> None:
        # Account1: 600 + 400 = 1000, Account2: 400
        self.assertEqual(self.account1.total_value(), Decimal("1000.00"))
        self.assertEqual(self.account2.total_value(), Decimal("400.00"))
        self.assertEqual(self.portfolio.total_value, Decimal("1400.00"))

        by_type = self.portfolio.value_by_account_type()
        self.assertEqual(by_type["ROTH_IRA"], Decimal("1000.00"))
        self.assertEqual(by_type["TAXABLE"], Decimal("400.00"))

    def test_value_and_allocation_by_asset_class(self) -> None:
        by_ac = self.portfolio.value_by_asset_class()
        # Stocks: 600 + 400 = 1000, Bonds: 400
        self.assertEqual(by_ac["US Stocks"], Decimal("1000.00"))
        self.assertEqual(by_ac["Bonds"], Decimal("400.00"))

        allocation = self.portfolio.allocation_by_asset_class()
        # Total 1400 -> Stocks ~71.428..., Bonds ~28.571...
        self.assertAlmostEqual(allocation["US Stocks"], Decimal("71.4285714"), places=5)
        self.assertAlmostEqual(allocation["Bonds"], Decimal("28.5714286"), places=5)

    def test_variance_from_targets(self) -> None:
        # Targets by account:
        # Account1: 50/50 stocks/bonds, Account2: 100% stocks
        effective_targets = {
            self.account1.id: {"US Stocks": Decimal("50"), "Bonds": Decimal("50")},
            self.account2.id: {"US Stocks": Decimal("100")},
        }

        variance = self.portfolio.variance_from_targets(effective_targets)

        # Total current: Stocks 1000, Bonds 400
        # Targets:
        #  - Account1 total 1000 -> 500 stocks, 500 bonds
        #  - Account2 total 400 -> 400 stocks
        # Combined target: Stocks 900, Bonds 500
        # Variance: Stocks +100, Bonds -100
        self.assertEqual(variance["US Stocks"], Decimal("100.00"))
        self.assertEqual(variance["Bonds"], Decimal("-100.00"))

    def test_account_lookup_helpers(self) -> None:
        self.assertEqual(self.portfolio.account_by_id(self.account1.id), self.account1)
        self.assertIsNone(self.portfolio.account_by_id(99999))

        accounts_by_type = self.portfolio.accounts_by_type("ROTH_IRA")
        self.assertIn(self.account1, accounts_by_type)
        self.assertNotIn(self.account2, accounts_by_type)

    def test_load_for_user_uses_manager(self) -> None:
        # Basic smoke test that load_for_user returns a portfolio
        portfolio = Portfolio.load_for_user(self.user)
        self.assertEqual(portfolio.user_id, self.user.id)
        # At least the two accounts created in setUp should be present
        self.assertGreaterEqual(len(portfolio.accounts), 2)

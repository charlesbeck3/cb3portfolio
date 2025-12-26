from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

import pytest

from portfolio.domain.portfolio import Portfolio
from portfolio.models import Account, AssetClass, Holding
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


@pytest.mark.domain
@pytest.mark.integration
class PortfolioTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)

        self.us_stocks = AssetClass.objects.create(
            name="US Stocks", category=self.category_us_equities
        )
        self.bonds = AssetClass.objects.create(name="Bonds", category=self.category_fixed_income)

        # Update seeded securities to use the test-specific asset classes
        self.vti.asset_class = self.us_stocks
        self.vti.save()
        self.bnd.asset_class = self.bonds
        self.bnd.save()

        self.acc_roth = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        self.acc_taxable = Account.objects.create(
            user=self.user,
            name="Taxable",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )

        # Roth: 6 shares @ 100 = 600 US Stocks
        Holding.objects.create(
            account=self.acc_roth,
            security=self.vti,
            shares=Decimal("6"),
            current_price=Decimal("100"),
        )
        # Taxable: 4 shares @ 100 = 400 Bonds
        Holding.objects.create(
            account=self.acc_taxable,
            security=self.bnd,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

    def test_len_and_iter(self) -> None:
        portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])
        self.assertEqual(len(portfolio), 2)
        self.assertEqual([a.id for a in portfolio], [self.acc_roth.id, self.acc_taxable.id])

    def test_total_value(self) -> None:
        portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])
        self.assertEqual(portfolio.total_value, Decimal("1000"))

    def test_value_by_account_type(self) -> None:
        portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])
        by_type = portfolio.value_by_account_type()
        self.assertEqual(by_type["ROTH_IRA"], Decimal("600"))
        self.assertEqual(by_type["TAXABLE"], Decimal("400"))

    def test_value_by_asset_class(self) -> None:
        portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])
        by_ac = portfolio.value_by_asset_class()
        self.assertEqual(by_ac["US Stocks"], Decimal("600"))
        self.assertEqual(by_ac["Bonds"], Decimal("400"))

    def test_allocation_by_asset_class(self) -> None:
        portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])
        alloc = portfolio.allocation_by_asset_class()
        self.assertEqual(alloc["US Stocks"].quantize(Decimal("0.01")), Decimal("60.00"))
        self.assertEqual(alloc["Bonds"].quantize(Decimal("0.01")), Decimal("40.00"))

    def test_account_by_id(self) -> None:
        portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])
        self.assertEqual(portfolio.account_by_id(self.acc_roth.id), self.acc_roth)
        self.assertIsNone(portfolio.account_by_id(999999))

    def test_accounts_by_type(self) -> None:
        portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])
        self.assertEqual(portfolio.accounts_by_type("ROTH_IRA"), [self.acc_roth])
        self.assertEqual(portfolio.accounts_by_type("TAXABLE"), [self.acc_taxable])

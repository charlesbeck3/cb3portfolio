from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.domain.analysis import PortfolioAnalysis
from portfolio.domain.portfolio import Portfolio
from portfolio.models import Account, AssetClass, Holding, Security
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


class PortfolioAnalysisTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")

        self.us_stocks = AssetClass.objects.create(name="US Stocks", category=self.cat_us_eq)
        self.bonds = AssetClass.objects.create(name="Bonds", category=self.cat_fi)

        self.vti = Security.objects.create(
            ticker="VTI",
            name="Vanguard Total Stock Market ETF",
            asset_class=self.us_stocks,
        )
        self.bnd = Security.objects.create(
            ticker="BND",
            name="Vanguard Total Bond Market ETF",
            asset_class=self.bonds,
        )

        self.acc_roth = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
            institution=self.institution,
        )
        self.acc_taxable = Account.objects.create(
            user=self.user,
            name="Taxable",
            account_type=self.type_taxable,
            institution=self.institution,
        )

        Holding.objects.create(
            account=self.acc_roth,
            security=self.vti,
            shares=Decimal("6"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=self.acc_taxable,
            security=self.bnd,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

        self.portfolio = Portfolio(user_id=self.user.id, accounts=[self.acc_roth, self.acc_taxable])

    def test_target_value_and_variance(self) -> None:
        analysis = PortfolioAnalysis(
            portfolio=self.portfolio,
            targets={
                "US Stocks": Decimal("50.00"),
                "Bonds": Decimal("50.00"),
            },
        )

        self.assertEqual(analysis.total_value, Decimal("1000"))

        self.assertEqual(analysis.target_value_for("US Stocks"), Decimal("500"))
        self.assertEqual(analysis.variance_for("US Stocks"), Decimal("100"))
        self.assertEqual(analysis.variance_pct_for("US Stocks").quantize(Decimal("0.01")), Decimal("10.00"))

        self.assertEqual(analysis.target_value_for("Bonds"), Decimal("500"))
        self.assertEqual(analysis.variance_for("Bonds"), Decimal("-100"))
        self.assertEqual(analysis.variance_pct_for("Bonds").quantize(Decimal("0.01")), Decimal("-10.00"))

    def test_variance_pct_for_zero_total(self) -> None:
        empty = Portfolio(user_id=self.user.id, accounts=[])
        analysis = PortfolioAnalysis(portfolio=empty, targets={"US Stocks": Decimal("50.00")})
        self.assertEqual(analysis.variance_pct_for("US Stocks"), Decimal("0.00"))

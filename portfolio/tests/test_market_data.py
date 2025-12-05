from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.market_data import MarketDataService
from portfolio.models import (
    Account,
    AssetCategory,
    AssetClass,
    Holding,
    Institution,
    Security,
)

from .base import PortfolioTestMixin

User = get_user_model()


class MarketDataServiceTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.institution = Institution.objects.create(name="Vanguard")
        self.category_us_equities = AssetCategory.objects.get(code='US_EQUITIES')
        self.category_fixed_income = AssetCategory.objects.get(code='FIXED_INCOME')
        self.asset_class_us = AssetClass.objects.create(name='US Stocks', category=self.category_us_equities)
        self.asset_class_bonds = AssetClass.objects.create(name='Bonds', category=self.category_fixed_income)
        self.account_roth = Account.objects.create(
            user=self.user, name='Roth IRA', account_type=self.type_roth, institution=self.institution
        )
        self.account_taxable = Account.objects.create(
            user=self.user, name='Taxable', account_type=self.type_taxable, institution=self.institution
        )
        self.sec_vti = Security.objects.create(ticker='VTI', name='Vanguard Total Stock Market', asset_class=self.asset_class_us)
        self.sec_bnd = Security.objects.create(ticker='BND', name='Vanguard Total Bond Market', asset_class=self.asset_class_bonds)
        self.holding_vti_roth = Holding.objects.create(
            account=self.account_roth, security=self.sec_vti, shares=Decimal('10.0'), current_price=Decimal('200.00')
        )
        self.holding_bnd_taxable = Holding.objects.create(
            account=self.account_taxable, security=self.sec_bnd, shares=Decimal('20.0'), current_price=Decimal('80.00')
        )

    @patch('portfolio.market_data.yf.download')
    def test_update_prices(self, mock_download: MagicMock) -> None:
        # Mock yfinance response
        mock_data = MagicMock()
        # Mocking .iloc[-1] to return a dict-like object or series
        mock_data.iloc.__getitem__.return_value = {'VTI': 210.00, 'BND': 85.00}
        mock_download.return_value = {'Close': mock_data}
        MarketDataService.update_prices(self.user)
        self.holding_vti_roth.refresh_from_db()
        self.holding_bnd_taxable.refresh_from_db()
        self.assertEqual(self.holding_vti_roth.current_price, Decimal('210.00'))
        self.assertEqual(self.holding_bnd_taxable.current_price, Decimal('85.00'))

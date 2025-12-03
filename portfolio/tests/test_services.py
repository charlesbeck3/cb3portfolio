from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import Account, AssetCategory, AssetClass, Holding, Security
from portfolio.services import PortfolioSummaryService

User = get_user_model()

class PortfolioSummaryServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='testuser', password='password')
        self.category_equities = AssetCategory.objects.get(code='EQUITIES')
        self.category_us_equities = AssetCategory.objects.get(code='US_EQUITIES')
        self.category_fixed_income = AssetCategory.objects.get(code='FIXED_INCOME')
        self.asset_class_us = AssetClass.objects.create(name='US Stocks', category=self.category_us_equities)
        self.asset_class_bonds = AssetClass.objects.create(name='Bonds', category=self.category_fixed_income)
        self.account_roth = Account.objects.create(
            user=self.user, name='Roth IRA', account_type='ROTH_IRA', tax_treatment='TAX_FREE'
        )
        self.account_taxable = Account.objects.create(
            user=self.user, name='Taxable', account_type='TAXABLE', tax_treatment='TAXABLE'
        )
        self.sec_vti = Security.objects.create(ticker='VTI', name='Vanguard Total Stock Market', asset_class=self.asset_class_us)
        self.sec_bnd = Security.objects.create(ticker='BND', name='Vanguard Total Bond Market', asset_class=self.asset_class_bonds)
        self.holding_vti_roth = Holding.objects.create(
            account=self.account_roth, security=self.sec_vti, shares=Decimal('10.0'), current_price=Decimal('200.00')
        )
        self.holding_bnd_taxable = Holding.objects.create(
            account=self.account_taxable, security=self.sec_bnd, shares=Decimal('20.0'), current_price=Decimal('80.00')
        )

    @patch('portfolio.services.yf.download')
    def test_update_prices(self, mock_download: MagicMock) -> None:
        # Mock yfinance response
        mock_data = MagicMock()
        # Mocking .iloc[-1] to return a dict-like object or series
        mock_data.iloc.__getitem__.return_value = {'VTI': 210.00, 'BND': 85.00}
        mock_download.return_value = {'Close': mock_data}
        PortfolioSummaryService.update_prices(self.user)
        self.holding_vti_roth.refresh_from_db()
        self.holding_bnd_taxable.refresh_from_db()
        self.assertEqual(self.holding_vti_roth.current_price, Decimal('210.00'))
        self.assertEqual(self.holding_bnd_taxable.current_price, Decimal('85.00'))

    @patch('portfolio.services.PortfolioSummaryService.update_prices')
    def test_get_holdings_summary(self, mock_update_prices: MagicMock) -> None:
        # Ensure prices are set (already set in setUp, but update_prices is mocked so they won't change)
        summary = PortfolioSummaryService.get_holdings_summary(self.user)
        # VTI in Roth: 10 * 200 = 2000
        # BND in Taxable: 20 * 80 = 1600
        # Check Grand Total
        self.assertEqual(summary['grand_total'], Decimal('3600.00'))
        # Check Account Type Grand Totals
        self.assertEqual(summary['account_type_grand_totals']['ROTH_IRA'], Decimal('2000.00'))
        self.assertEqual(summary['account_type_grand_totals']['TAXABLE'], Decimal('1600.00'))
        # Check Categories
        equities = summary['categories']['US_EQUITIES']
        self.assertEqual(equities['total'], Decimal('2000.00'))
        self.assertEqual(equities['asset_classes']['US Stocks']['total'], Decimal('2000.00'))
        self.assertEqual(equities['asset_classes']['US Stocks']['account_types']['ROTH_IRA'], Decimal('2000.00'))
        fixed_income = summary['categories']['FIXED_INCOME']
        self.assertEqual(fixed_income['total'], Decimal('1600.00'))
        self.assertEqual(fixed_income['asset_classes']['Bonds']['total'], Decimal('1600.00'))
        self.assertEqual(fixed_income['asset_classes']['Bonds']['account_types']['TAXABLE'], Decimal('1600.00'))
        equities_group = summary['groups']['EQUITIES']
        self.assertEqual(equities_group['label'], 'Equities')
        self.assertEqual(equities_group['total'], Decimal('2000.00'))
        self.assertIn('US_EQUITIES', equities_group['categories'])

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import (
    Account,
    AssetCategory,
    AssetClass,
    Holding,
    Institution,
    Security,
    TargetAllocation,
)
from portfolio.services import PortfolioSummaryService

from .base import PortfolioTestMixin

User = get_user_model()


class PortfolioSummaryServiceTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.institution = Institution.objects.create(name="Vanguard")

        # Create Assets
        self.category_equities = AssetCategory.objects.get(code='EQUITIES')
        self.category_us_equities = AssetCategory.objects.get(code='US_EQUITIES')
        self.category_fixed_income = AssetCategory.objects.get(code='FIXED_INCOME')
        self.asset_class_us = AssetClass.objects.create(name='US Stocks', category=self.category_us_equities)
        self.asset_class_bonds = AssetClass.objects.create(name='Bonds', category=self.category_fixed_income)

        # Create Account using AccountType object
        self.account_roth = Account.objects.create(
            user=self.user, name='Roth IRA', account_type=self.type_roth, institution=self.institution
        )
        self.account_taxable = Account.objects.create(
            user=self.user, name='Taxable', account_type=self.type_taxable, institution=self.institution
        )

        # Create Securities
        self.sec_vti = Security.objects.create(ticker='VTI', name='Vanguard Total Stock Market', asset_class=self.asset_class_us)
        self.sec_bnd = Security.objects.create(ticker='BND', name='Vanguard Total Bond Market', asset_class=self.asset_class_bonds)

        # Create Holdings
        self.holding_vti_roth = Holding.objects.create(
            account=self.account_roth, security=self.sec_vti, shares=Decimal('10.0'), current_price=Decimal('200.00')
        )
        self.holding_bnd_taxable = Holding.objects.create(
            account=self.account_taxable, security=self.sec_bnd, shares=Decimal('20.0'), current_price=Decimal('80.00')
        )

    @patch('portfolio.market_data.MarketDataService.update_prices')
    def test_get_holdings_summary(self, mock_update_prices: MagicMock) -> None:
        # Ensure prices are set (already set in setUp, but update_prices is mocked so they won't change)
        summary = PortfolioSummaryService.get_holdings_summary(self.user)
        # VTI in Roth: 10 * 200 = 2000
        # BND in Taxable: 20 * 80 = 1600
        # Check Grand Total
        self.assertEqual(summary.grand_total, Decimal('3600.00'))
        # Check Account Type Grand Totals
        self.assertEqual(summary.account_type_grand_totals['ROTH_IRA'], Decimal('2000.00'))
        self.assertEqual(summary.account_type_grand_totals['TAXABLE'], Decimal('1600.00'))
        # Check Categories
        equities = summary.categories['US_EQUITIES']
        self.assertEqual(equities.total, Decimal('2000.00'))
        equities_us = equities.asset_classes['US Stocks']
        self.assertEqual(equities_us.total, Decimal('2000.00'))
        self.assertEqual(equities_us.account_types['ROTH_IRA'].current, Decimal('2000.00'))
        fixed_income = summary.categories['FIXED_INCOME']
        self.assertEqual(fixed_income.total, Decimal('1600.00'))
        fixed_income_bonds = fixed_income.asset_classes['Bonds']
        self.assertEqual(fixed_income_bonds.total, Decimal('1600.00'))
        self.assertEqual(fixed_income_bonds.account_types['TAXABLE'].current, Decimal('1600.00'))
        equities_group = summary.groups['EQUITIES']
        self.assertEqual(equities_group.label, 'Equities')
        self.assertEqual(equities_group.total, Decimal('2000.00'))
        self.assertIn('US_EQUITIES', equities_group.categories)
        self.assertEqual(equities_group.total, Decimal('2000.00'))
        self.assertIn('US_EQUITIES', equities_group.categories)

        # Check account type percentage share of grand total (rounded to 2 decimal places)
        percentages = summary.account_type_percentages
        self.assertEqual(percentages['ROTH_IRA'].quantize(Decimal('0.01')), Decimal('55.56'))
        self.assertEqual(percentages['TAXABLE'].quantize(Decimal('0.01')), Decimal('44.44'))

    @patch('portfolio.market_data.MarketDataService.update_prices')
    def test_get_holdings_summary_with_targets_and_variance(self, mock_update_prices: MagicMock) -> None:
        """Target allocations should produce target dollar amounts and zero variance when aligned."""

        # Set simple 100% targets for each account type and asset class
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class_us,
            target_pct=Decimal('100.0'),
        )
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_taxable,
            asset_class=self.asset_class_bonds,
            target_pct=Decimal('100.0'),
        )

        summary = PortfolioSummaryService.get_holdings_summary(self.user)

        # Grand totals
        self.assertEqual(summary.grand_total, Decimal('3600.00'))
        self.assertEqual(summary.grand_target_total, Decimal('3600.00'))
        self.assertEqual(summary.grand_variance_total, Decimal('0.00'))

        # Account-type level target and variance totals
        self.assertEqual(summary.account_type_grand_target_totals['ROTH_IRA'], Decimal('2000.00'))
        self.assertEqual(summary.account_type_grand_target_totals['TAXABLE'], Decimal('1600.00'))
        self.assertEqual(summary.account_type_grand_variance_totals['ROTH_IRA'], Decimal('0.00'))
        self.assertEqual(summary.account_type_grand_variance_totals['TAXABLE'], Decimal('0.00'))

        # Category-level rollups
        equities = summary.categories['US_EQUITIES']
        equities_targets = equities.account_type_target_totals
        equities_variances = equities.account_type_variance_totals
        self.assertEqual(equities_targets['ROTH_IRA'], Decimal('2000.00'))
        self.assertEqual(equities_variances['ROTH_IRA'], Decimal('0.00'))

        fixed_income = summary.categories['FIXED_INCOME']
        fixed_income_targets = fixed_income.account_type_target_totals
        fixed_income_variances = fixed_income.account_type_variance_totals
        self.assertEqual(fixed_income_targets['TAXABLE'], Decimal('1600.00'))
        self.assertEqual(fixed_income_variances['TAXABLE'], Decimal('0.00'))

        # Asset-class level target and variance
        equities_us = equities.asset_classes['US Stocks']
        roth_data = equities_us.account_types['ROTH_IRA']
        self.assertEqual(roth_data.current, Decimal('2000.00'))
        self.assertEqual(roth_data.target, Decimal('2000.00'))
        self.assertEqual(roth_data.variance, Decimal('0.00'))

        fixed_income_bonds = fixed_income.asset_classes['Bonds']
        taxable_data = fixed_income_bonds.account_types['TAXABLE']
        self.assertEqual(taxable_data.current, Decimal('1600.00'))
        self.assertEqual(taxable_data.target, Decimal('1600.00'))
        self.assertEqual(taxable_data.variance, Decimal('0.00'))

    @patch('portfolio.market_data.MarketDataService.update_prices')
    def test_get_account_summary(self, mock_update_prices: MagicMock) -> None:
        summary = PortfolioSummaryService.get_account_summary(self.user)

        # Check grand total
        self.assertEqual(summary['grand_total'], Decimal('3600.00'))

        # Check groups
        groups = summary['groups']
        self.assertIn('Retirement', groups)
        self.assertIn('Investments', groups)

        retirement = groups['Retirement']
        self.assertEqual(retirement['total'], Decimal('2000.00'))
        self.assertEqual(len(retirement['accounts']), 1)
        self.assertEqual(retirement['accounts'][0]['name'], 'Roth IRA')

        investments = groups['Investments']
        self.assertEqual(investments['total'], Decimal('1600.00'))
        self.assertEqual(len(investments['accounts']), 1)
        self.assertEqual(investments['accounts'][0]['name'], 'Taxable')

    @patch('portfolio.market_data.MarketDataService.update_prices')
    def test_get_holdings_by_category(self, mock_update_prices: MagicMock) -> None:
        result = PortfolioSummaryService.get_holdings_by_category(self.user)

        grand_total = result['grand_total']
        self.assertEqual(grand_total, Decimal('3600.00'))

        holding_groups = result['holding_groups']

        # Check Equities Group
        self.assertIn('EQUITIES', holding_groups)
        equities_group = holding_groups['EQUITIES']
        self.assertEqual(equities_group.label, 'Equities')
        self.assertEqual(equities_group.total, Decimal('2000.00'))

        # Check US Equities Category within Equities Group
        self.assertIn('US_EQUITIES', equities_group.categories)
        us_equities = equities_group.categories['US_EQUITIES']
        self.assertEqual(us_equities.label, 'US Equities')
        self.assertEqual(us_equities.total, Decimal('2000.00'))
        self.assertEqual(len(us_equities.holdings), 1)

        vti_holding = us_equities.holdings[0]
        self.assertEqual(vti_holding.ticker, 'VTI')
        self.assertEqual(vti_holding.value, Decimal('2000.00'))

        # Check Fixed Income Group
        self.assertIn('FIXED_INCOME', holding_groups)
        fixed_income_group = holding_groups['FIXED_INCOME']
        self.assertEqual(fixed_income_group.label, 'Fixed Income')
        self.assertEqual(fixed_income_group.total, Decimal('1600.00'))

        # Check Fixed Income Category
        self.assertIn('FIXED_INCOME', fixed_income_group.categories)
        fi_category = fixed_income_group.categories['FIXED_INCOME']
        self.assertEqual(fi_category.total, Decimal('1600.00'))
        self.assertEqual(len(fi_category.holdings), 1)

        bnd_holding = fi_category.holdings[0]
        self.assertEqual(bnd_holding.ticker, 'BND')
        self.assertEqual(bnd_holding.value, Decimal('1600.00'))

    @patch('portfolio.market_data.MarketDataService.update_prices')
    def test_get_account_summary_sorting(self, mock_update_prices: MagicMock) -> None:
        # Create a third account type with a middle value to verify sorting
        # Roth: 2000 (Retirement)
        # Taxable: 1600 (Investments)
        # Let's add a Cash account with 3000 (Cash) to be the top

        # Note: The service uses a hardcoded map for account types to groups.
        # 'ROTH_IRA' -> 'Retirement'
        # 'TAXABLE' -> 'Investments'
        # We need to ensure we can map to 'Cash' or just use the existing groups with different totals.
        # The service defaults to 'Investments' if not found in map, but we want to test sorting of groups.
        # Let's just manipulate the existing accounts to change totals.

        # Make Taxable (Investments) the largest
        self.holding_bnd_taxable.shares = Decimal('100.0') # 100 * 80 = 8000
        self.holding_bnd_taxable.save()

        # Roth (Retirement) is 2000

        summary = PortfolioSummaryService.get_account_summary(self.user)
        groups = list(summary['groups'].keys())

        # Expect Investments (8000) then Retirement (2000)
        self.assertEqual(groups, ['Investments', 'Retirement'])

        # Now make Roth (Retirement) the largest
        self.holding_vti_roth.shares = Decimal('100.0') # 100 * 200 = 20000
        self.holding_vti_roth.save()

        summary = PortfolioSummaryService.get_account_summary(self.user)
        groups = list(summary['groups'].keys())

        # Expect Retirement (20000) then Investments (8000)
        self.assertEqual(groups, ['Retirement', 'Investments'])

    @patch('portfolio.market_data.MarketDataService.update_prices')
    def test_get_account_summary_absolute_deviation(self, mock_update_prices: MagicMock) -> None:
        """Test absolute deviation calculation."""
        # Setup specific scenario for Roth Account
        # Total Value: $100
        # US Stock: $60 (Target 50% -> $50) -> Dev 10
        # Bonds: $40 (Target 50% -> $50) -> Dev 10
        # Total Dev: 20

        # Modify existing holding (US Stocks)
        self.holding_vti_roth.current_price = Decimal('1.00')
        self.holding_vti_roth.shares = Decimal('60.00')
        self.holding_vti_roth.save()

        # Add new holding (Bonds) to same account
        Holding.objects.create(
            account=self.account_roth,
            security=self.sec_bnd,
            shares=Decimal('40.00'),
            current_price=Decimal('1.00')
        )

        # Create Targets
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class_us,
            target_pct=Decimal('50.0')
        )
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class_bonds,
            target_pct=Decimal('50.0')
        )

        summary = PortfolioSummaryService.get_account_summary(self.user)

        # Find Roth account
        roth_account = None
        for group in summary['groups'].values():
            for acc in group['accounts']:
                if acc['name'] == 'Roth IRA':
                    roth_account = acc
                    break

        self.assertIsNotNone(roth_account)
        assert roth_account is not None
        self.assertEqual(roth_account['total'], Decimal('100.00'))
        self.assertEqual(roth_account['absolute_deviation'], Decimal('20.00'))
        self.assertEqual(roth_account['absolute_deviation_pct'], Decimal('20.00'))

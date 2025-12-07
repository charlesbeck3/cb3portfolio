import unittest.mock
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import (
    Account,
    AssetCategory,
    AssetClass,
    Holding,
    Security,
    TargetAllocation,
)

from .base import PortfolioTestMixin

User = get_user_model()

class TargetAllocationViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_login(self.user)

        # Setup Assets
        self.cat_eq, _ = AssetCategory.objects.get_or_create(code='EQUITIES', defaults={'label': 'Equities', 'sort_order': 1})
        self.ac_us, _ = AssetClass.objects.get_or_create(name='US Stocks', defaults={'category': self.cat_eq})
        self.sec_vti, _ = Security.objects.get_or_create(ticker='VTI', defaults={'name': 'VTI', 'asset_class': self.ac_us})

        self.cat_cash, _ = AssetCategory.objects.get_or_create(code='CASH', defaults={'label': 'Cash', 'sort_order': 10})
        self.ac_cash, _ = AssetClass.objects.get_or_create(name='Cash', defaults={'category': self.cat_cash})
        self.sec_cash, _ = Security.objects.get_or_create(ticker='CASH', defaults={'name': 'Cash', 'asset_class': self.ac_cash})

        # Setup Accounts
        self.acc_roth = Account.objects.create(
            user=self.user,
            name='My Roth',
            account_type=self.type_roth,
            institution=self.institution
        )
        self.acc_tax = Account.objects.create(
            user=self.user,
            name='My Taxable',
            account_type=self.type_taxable,
            institution=self.institution
        )

        # Setup Holdings
        # Roth: $6000 VTI
        Holding.objects.create(account=self.acc_roth, security=self.sec_vti, shares=60, current_price=100)
        # Taxable: $2000 VTI, $2000 Cash
        Holding.objects.create(account=self.acc_tax, security=self.sec_vti, shares=20, current_price=100)
        Holding.objects.create(account=self.acc_tax, security=self.sec_cash, shares=2000, current_price=1)

        # Total Portfolio: $10,000
        # Roth (60%): $6000
        # Taxable (40%): $4000

    def test_initial_calculation(self) -> None:
        """Verify context data calculations for portfolio totals and maps."""
        url = reverse('portfolio:target_allocations')

        # Patch get_prices to return stable values matching setUp
        with unittest.mock.patch('portfolio.services.MarketDataService.get_prices') as mock_prices:
             mock_prices.return_value = {'VTI': Decimal('100.00'), 'CASH': Decimal('1.00')}
             response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        context = response.context
        self.assertEqual(context['portfolio_total_value'], Decimal('10000.00'))

        # Verify Account Types in Context
        # Structure: context['account_types'] -> list of AT objects with 'active_accounts' attached
        account_types = {at.code: at for at in context['account_types']}

        self.assertIn('ROTH_IRA', account_types)
        self.assertIn('TAXABLE', account_types)

        roth = account_types['ROTH_IRA']
        taxable = account_types['TAXABLE']

        # ROTH: Total $6000.
        # Allocation Map: US Stocks = 100% (since it's all VTI)
        self.assertEqual(roth.current_total_value, Decimal('6000.00'))
        self.assertAlmostEqual(roth.allocation_map[self.ac_us.id], 100.0)

        # TAXABLE: Total $4000.
        # Allocation Map: VTI ($2000) = 50%, Cash ($2000) = 50%
        self.assertEqual(taxable.current_total_value, Decimal('4000.00'))
        self.assertAlmostEqual(taxable.allocation_map[self.ac_us.id], 50.0)
        self.assertAlmostEqual(taxable.allocation_map[self.ac_cash.id], 50.0)

    def test_save_defaults(self) -> None:
        """Verify saving account type defaults."""
        url = reverse('portfolio:target_allocations')

        # Inputs for ROTH: 80% US Stocks. (Implies 20% Cash)
        # Inputs for TAXABLE: 60% US Stocks. (Implies 40% Cash)
        data = {
            f'target_{self.type_roth.id}_{self.ac_us.id}': '80',
            f'target_{self.type_taxable.id}_{self.ac_us.id}': '60',
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        # Verify DB
        t_roth = TargetAllocation.objects.get(user=self.user, account_type=self.type_roth, asset_class=self.ac_us)
        self.assertEqual(t_roth.target_pct, Decimal('80.00'))

        t_roth_cash = TargetAllocation.objects.get(user=self.user, account_type=self.type_roth, asset_class=self.ac_cash)
        self.assertEqual(t_roth_cash.target_pct, Decimal('20.00')) # 100 - 80

        t_tax = TargetAllocation.objects.get(user=self.user, account_type=self.type_taxable, asset_class=self.ac_us)
        self.assertEqual(t_tax.target_pct, Decimal('60.00'))

    def test_save_overrides(self) -> None:
        """Verify saving account overrides (Full Override Mode)."""
        url = reverse('portfolio:target_allocations')

        # Override ROTH Account explicitly: 90% US Stocks
        # We need to provide inputs for the specific account.
        data = {
            f'target_account_{self.acc_roth.id}_{self.ac_us.id}': '90',
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        # Verify DB - Should have Account-specific target
        t_acc = TargetAllocation.objects.get(user=self.user, account=self.acc_roth, asset_class=self.ac_us)
        self.assertEqual(t_acc.target_pct, Decimal('90.00'))

        # Implicit Cash for Account Override
        t_acc_cash = TargetAllocation.objects.get(user=self.user, account=self.acc_roth, asset_class=self.ac_cash)
        self.assertEqual(t_acc_cash.target_pct, Decimal('10.00')) # 100 - 90

    def test_validation_negative(self) -> None:
        """Verify negative inputs are rejected."""
        url = reverse('portfolio:target_allocations')
        data = {
            f'target_{self.type_roth.id}_{self.ac_us.id}': '-10',
        }
        response = self.client.post(url, data)
        # Should redirect with error
        self.assertRedirects(response, url)

        if response.context:
            _ = response.context['messages']
        # Since redirect, we might need to check messages in subsequent request or use folow=True
        # But standard Django test client handles it if we follow?

        # Let's check objects not created
        self.assertFalse(TargetAllocation.objects.exists())

    def test_validation_over_100(self) -> None:
        """Verify allocations over 100% trigger warning/error."""
        # Current implementation logic:
        # "Total allocation ... exceeds 100%" error message added to list.
        # See views.py line 367.

        url = reverse('portfolio:target_allocations')
        data = {
            f'target_{self.type_roth.id}_{self.ac_us.id}': '110',
        }
        response = self.client.post(url, data, follow=True)

        # Should have error message
        messages = list(response.context['messages'])
        self.assertTrue(any("exceeds 100%" in str(m) for m in messages))

        # Should NOT save
        self.assertFalse(TargetAllocation.objects.exists())

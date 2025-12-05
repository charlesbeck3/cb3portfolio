from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import Account

from .base import PortfolioTestMixin

User = get_user_model()

class DashboardViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_login(self.user)

        # Create an account for Roth only.
        # The mixin creates 4 types: Roth, Trad, Taxable, 401k.
        Account.objects.create(
            user=self.user,
            name='My Roth',
            account_type=self.type_roth,
            institution=self.institution
        )

    def test_account_types_context_filtering(self) -> None:
        """
        Verify that only account types with associated accounts for the user
        are included in the context.
        """
        url = reverse('portfolio:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Extract account_types from context
        # It is a QuerySet or list of tuples (code, label)
        account_types = response.context['account_types']
        # Convert to list of codes for easy checking
        codes = [item[0] for item in account_types] # item is (code, label)

        self.assertIn('ROTH_IRA', codes)
        self.assertNotIn('TRADITIONAL_IRA', codes)
        self.assertNotIn('TAXABLE', codes)
        self.assertNotIn('401K', codes)


class HoldingsViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_login(self.user)
        
        self.account = Account.objects.create(
            user=self.user,
            name='My Roth',
            account_type=self.type_roth,
            institution=self.institution
        )

    def test_holdings_view(self) -> None:
        url = reverse('portfolio:holdings')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portfolio/holdings.html')
        self.assertIn('holding_groups', response.context)
        self.assertIn('sidebar_data', response.context)
        # Account should not be in context
        self.assertNotIn('account', response.context)

    def test_holdings_view_with_account(self) -> None:
        url = reverse('portfolio:account_holdings', args=[self.account.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portfolio/holdings.html')
        self.assertIn('account', response.context)
        self.assertEqual(response.context['account'], self.account)

    def test_holdings_view_invalid_account(self) -> None:
        # Should suppress DoesNotExist
        url = reverse('portfolio:account_holdings', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('account', response.context)

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import Account, AccountGroup, Institution
from portfolio.services import PortfolioSummaryService

User = get_user_model()

class AccountGroupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.institution = Institution.objects.create(name='Test Bank')

        # Groups created by migration should exist, but let's ensure/create for test isolation if needed
        # Or better, just rely on the fact we can create them.
        # Since tests run with empty DB, the migration run might not populate unless we use TransactionTestCase or similar,
        # but standard TestCase usually applies migrations.
        # Actually, standard Django tests run migrations.
        # Let's verify standard groups exist.

        self.ret_group = AccountGroup.objects.get(name='Retirement')
        self.inv_group = AccountGroup.objects.get(name='Investments')
        self.dep_group = AccountGroup.objects.get(name='Deposit Accounts') # This is the NEW one

    def test_account_grouping(self):
        # Create accounts assigned to different groups
        Account.objects.create(
            user=self.user,
            name='Roth',
            account_type='ROTH_IRA',
            institution=self.institution,
            group=self.ret_group
        )
        Account.objects.create(
            user=self.user,
            name='Brokerage',
            account_type='TAXABLE',
            institution=self.institution,
            group=self.inv_group
        )
        Account.objects.create(
            user=self.user,
            name='Savings',
            account_type='TAXABLE',
            institution=self.institution,
            group=self.dep_group
        )

        # Accounts without group (should go to Other)
        Account.objects.create(
            user=self.user,
            name='Mystery',
            account_type='TAXABLE',
            institution=self.institution,
            group=None
        )

        summary = PortfolioSummaryService.get_account_summary(self.user)
        groups = summary['groups']

        # Check Retirement
        self.assertIn('Retirement', groups)
        self.assertEqual(len(groups['Retirement']['accounts']), 1)
        self.assertEqual(groups['Retirement']['accounts'][0]['name'], 'Roth')

        # Check Investments
        self.assertIn('Investments', groups)
        self.assertEqual(len(groups['Investments']['accounts']), 1)
        self.assertEqual(groups['Investments']['accounts'][0]['name'], 'Brokerage')

        # Check Deposit Accounts (The NEW feature)
        self.assertIn('Deposit Accounts', groups)
        self.assertEqual(len(groups['Deposit Accounts']['accounts']), 1)
        self.assertEqual(groups['Deposit Accounts']['accounts'][0]['name'], 'Savings')

        # Check Other
        self.assertIn('Other', groups)
        self.assertEqual(len(groups['Other']['accounts']), 1)
        self.assertEqual(groups['Other']['accounts'][0]['name'], 'Mystery')

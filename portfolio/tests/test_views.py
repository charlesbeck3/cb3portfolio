from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import Account, AccountType, AssetCategory, AssetClass, Holding, Security

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
    def test_redundant_totals(self) -> None:
        """
        Verify that redundant total rows are suppressed:
        1. Category Total hidden if Category has only 1 Asset Class.
        2. Group Total hidden if Group has only 1 Asset Class (total).
        """
        # --- Setup Data ---

        # 1. Single Asset Group (simulating Cash)
        # Group 'Deposit Accounts' (self.group_dep) created in mixin.
        # Create Category 'Cash' -> 1 Asset Class 'Cash' -> 1 Security 'CASH'
        cat_cash, _ = AssetCategory.objects.get_or_create(code='CASH', defaults={'label': 'Cash', 'sort_order': 10})
        ac_cash, _ = AssetClass.objects.get_or_create(name='Cash', defaults={'category': cat_cash, 'expected_return': 0})
        sec_cash, _ = Security.objects.get_or_create(ticker='CASH', defaults={'name': 'Cash Holding', 'asset_class': ac_cash})

        # Create Holding in a Deposit Account
        acc_dep = Account.objects.create(
            user=self.user,
            name='My Cash',
            account_type=AccountType.objects.get(code='TAXABLE'), # Using TAXABLE for simplicity, technically could be DEPOSIT
            institution=self.institution
        )
        Holding.objects.create(account=acc_dep, security=sec_cash, shares=100, current_price=1)

        # 2. Multi-Asset Group
        # Group 'Investments' (self.group_inv).
        # Category 'Equities' -> 2 Asset Classes 'US Stocks', 'Intl Stocks'
        cat_eq, _ = AssetCategory.objects.get_or_create(code='EQUITIES', defaults={'label': 'Equities', 'sort_order': 1})
        # Link category to group? The link is via AssetCategory.parent??
        # Logic in services.py: group = category.parent or category.
        # But wait, Group is AccountGroup, Category is AssetCategory.
        # services.py maps: group_code = category.parent or category.code
        # And summary.groups keys are these codes.
        # BUT AccountGroup logic in get_account_summary is different from get_holdings_summary?
        # Re-read services.py:
        # _build_category_maps loops categories. group = category.parent or category.
        # This means "Group" in the dashboard holdings table is actually the Parent Category (if exists) or the Category itself.
        # It is NOT AccountGroup.

        # So "Cash" scenario: Category 'Cash' (parent=None). Group Code = 'CASH'.
        # It has 1 Asset Class.
        # So Group 'CASH' has 1 Asset Class.

        # "Investments" scenario?
        # If we have US Equities (parent=Equities) and Intl Equities (parent=Equities).
        # Group Code = 'Equities'.
        # Group 'Equities' has 2 Categories (US, Intl) -> Multiple Asset Classes (>=2).
        # So Group Total for 'Equities' should be SHOWN.

        # Let's create 'Equities' Parent Category
        cat_parent_eq, _ = AssetCategory.objects.get_or_create(code='EQUITIES', defaults={'label': 'Equities Parent', 'sort_order': 1})

        # Sub-category 1: US Equities
        cat_us, _ = AssetCategory.objects.get_or_create(code='US_EQ', defaults={'label': 'US Equities', 'parent': cat_parent_eq, 'sort_order': 1})
        ac_us, _ = AssetClass.objects.get_or_create(name='US Stocks', defaults={'category': cat_us, 'expected_return': 0.1})
        sec_us, _ = Security.objects.get_or_create(ticker='VTI', defaults={'name': 'VTI', 'asset_class': ac_us})
        Holding.objects.create(account=acc_dep, security=sec_us, shares=10, current_price=100)

        # Sub-category 2: Intl Equities
        cat_intl, _ = AssetCategory.objects.get_or_create(code='INTL_EQ', defaults={'label': 'Intl Equities', 'parent': cat_parent_eq, 'sort_order': 2})
        ac_intl, _ = AssetClass.objects.get_or_create(name='Intl Stocks', defaults={'category': cat_intl, 'expected_return': 0.1})
        sec_intl, _ = Security.objects.get_or_create(ticker='VXUS', defaults={'name': 'VXUS', 'asset_class': ac_intl})
        Holding.objects.create(account=acc_dep, security=sec_intl, shares=10, current_price=50)

        # --- Execute ---
        response = self.client.get(reverse('portfolio:dashboard'))
        content = response.content.decode('utf-8')

        # --- Assertions ---

        # 1. Cash Scenario (Single Asset Class in Group 'CASH')
        # Asset Class 'Cash' should be present
        self.assertIn('Cash', content)
        # Category Total 'Cash Total' should NOT be present (Category has 1 AC)
        # Group Total 'Cash Total' should NOT be present (Group has 1 AC)
        # Note: If label is "Cash", total row is "Cash Total".
        self.assertNotIn('Cash Total', content, "Redundant Total row for Cash should be hidden.")

        # 2. Equities Scenario (Multi Asset Class in Group 'EQUITIES')
        # Category 'US Equities' has 1 Asset Class -> 'US Equities Total' should be HIDDEN
        # The Category Label itself is also hidden in this case because it's only shown in the subtotal row or if explicitly headered (which it isn't).
        # self.assertIn('US Equities', content)
        self.assertNotIn('US Equities Total', content, "Redundant Category Total for US Equities should be hidden.")

        # Group 'Equities Parent' has 2 Asset Classes (US Stocks + Intl Stocks) -> Group Total SHOWN
        self.assertIn('Equities Total', content, "Group Total for Equities should be shown.")


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

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import Account, AccountGroup, AccountType

from .base import PortfolioTestMixin

User = get_user_model()


class AccountGroupTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        # self.institution = Institution.objects.create(name='Test Bank')

        self.client.force_login(self.user)

        # Create basic account instances for testing grouping logic
        # Using types from mixin:
        # type_roth (Retirement), type_trad (Retirement),
        # type_taxable (Investments), type_401k (Retirement)
        # Mixin also creates: group_ret, group_inv, group_dep ('Deposit Accounts')

        # We need to manually add a "Cash" / "Deposit" type if we want to test that group fully,
        # but the mixin doesn't create a 'BANK' type by default?
        # Let's check base.py content if needed. Assuming standard mixin usage.

        # Create accounts
        Account.objects.create(
            user=self.user,
            name="Roth",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        Account.objects.create(
            user=self.user,
            name="Trad",
            portfolio=self.portfolio,
            account_type=self.type_trad,
            institution=self.institution,
        )
        Account.objects.create(
            user=self.user,
            name="Taxable",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )

        # Create a Savings account type and account for Deposit group
        self.type_savings = AccountType.objects.create(
            code="SAVINGS", label="Savings", group=self.group_deposits, tax_treatment="TAXABLE"
        )
        Account.objects.create(
            user=self.user,
            name="Savings",
            portfolio=self.portfolio,
            account_type=self.type_savings,
            institution=self.institution,
        )

    def test_account_grouping(self) -> None:
        # We can't easily create an "Other" account now unless we create a Type that has no Group?
        # Or if we create a type linked to a group that we don't check?
        # Or if we create a type with a null group (if allowed)?
        # AccountType.group is PROTECT, so it must exist.
        # So "Other" only happens if we delete a group? Or if we add a new Group that isn't in our test checks?
        # Let's create a "Mystery" type linked to a new Mystery group

        mystery_group = AccountGroup.objects.create(name="Mystery Group", sort_order=99)
        mystery_type = AccountType.objects.create(
            code="MYSTERY", label="Mystery", group=mystery_group, tax_treatment="TAXABLE"
        )

        Account.objects.create(
            user=self.user,
            name="Mystery Account",
            portfolio=self.portfolio,
            account_type=mystery_type,
            institution=self.institution,
        )

        # Verify using Dashboard View
        # Since logic is in get_sidebar_context mixin used by Dashboard

        response = self.client.get("/")  # Dashboard URL
        self.assertEqual(response.status_code, 200)

        sidebar_data = response.context["sidebar_data"]
        groups = sidebar_data["groups"]

        # Check Retirement
        self.assertIn("Retirement", groups)
        self.assertEqual(len(groups["Retirement"]["accounts"]), 2)

        # Check Investments
        self.assertIn("Investments", groups)
        self.assertEqual(len(groups["Investments"]["accounts"]), 1)
        self.assertEqual(groups["Investments"]["accounts"][0]["name"], "Taxable")

        # Check Deposits
        self.assertIn("Deposits", groups)
        self.assertEqual(len(groups["Deposits"]["accounts"]), 1)
        self.assertEqual(groups["Deposits"]["accounts"][0]["name"], "Savings")

        # Check Mystery Group
        self.assertIn("Mystery Group", groups)
        self.assertEqual(len(groups["Mystery Group"]["accounts"]), 1)
        self.assertEqual(groups["Mystery Group"]["accounts"][0]["name"], "Mystery Account")

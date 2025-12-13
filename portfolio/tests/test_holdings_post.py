from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from portfolio.models import Account, AccountType, Holding, Security, AssetClass, AssetCategory
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()

class HoldingsViewPostTests(TestCase, PortfolioTestMixin):
    def setUp(self):
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.force_login(self.user)

        self.account = Account.objects.create(
            user=self.user,
            name="My Roth",
            account_type=self.type_roth,
            institution=self.institution,
        )

        # Create a security to add
        self.cat_eq, _ = AssetCategory.objects.get_or_create(code="EQUITIES", defaults={"label": "Equities"})
        self.ac_us, _ = AssetClass.objects.get_or_create(name="US Stocks", defaults={"category": self.cat_eq})
        self.sec_us, _ = Security.objects.get_or_create(ticker="VTI", defaults={"name": "VTI", "asset_class": self.ac_us})

    def test_add_holding_success(self):
        url = reverse("portfolio:account_holdings", args=[self.account.id])
        data = {
            "security_id": self.sec_us.id,
            "initial_shares": "10.00"
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, f"Added {self.sec_us.ticker} to account.")
        
        holding = Holding.objects.get(account=self.account, security=self.sec_us)
        self.assertEqual(holding.shares, Decimal("10.00"))

    def test_add_holding_existing_warning(self):
        # Create holding first
        Holding.objects.create(account=self.account, security=self.sec_us, shares=5)

        url = reverse("portfolio:account_holdings", args=[self.account.id])
        data = {
            "security_id": self.sec_us.id,
            "initial_shares": "10.00" # Attempt to add duplicate
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, f"Holding for {self.sec_us.ticker} already exists")
        
        # Shares should remain unchanged
        holding = Holding.objects.get(account=self.account, security=self.sec_us)
        self.assertEqual(holding.shares, Decimal("5.00"))

    def test_add_holding_invalid_form(self):
        url = reverse("portfolio:account_holdings", args=[self.account.id])
        # Missing initial_shares
        data = {
            "security_id": self.sec_us.id,
        }
        response = self.client.post(url, data, follow=True)
        # Should show error form validation error
        # "This field is required." for initial_shares
        self.assertContains(response, "This field is required")

    def test_delete_holding(self):
        Holding.objects.create(account=self.account, security=self.sec_us, shares=5)
        
        url = reverse("portfolio:account_holdings", args=[self.account.id])
        data = {
            "delete_ticker": "VTI"
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Removed VTI from account")
        self.assertFalse(Holding.objects.filter(account=self.account, security=self.sec_us).exists())

    def test_bulk_update_shares(self):
        h1 = Holding.objects.create(account=self.account, security=self.sec_us, shares=5)
        
        # Another security
        sec_vxus = Security.objects.create(ticker="VXUS", name="VXUS", asset_class=self.ac_us)
        h2 = Holding.objects.create(account=self.account, security=sec_vxus, shares=10)

        url = reverse("portfolio:account_holdings", args=[self.account.id])
        data = {
            f"shares_{self.sec_us.ticker}": "7.5",
            f"shares_{sec_vxus.ticker}": "12.0",
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Updated 2 holdings")

        h1.refresh_from_db()
        h2.refresh_from_db()
        self.assertEqual(h1.shares, Decimal("7.5"))
        self.assertEqual(h2.shares, Decimal("12.0"))

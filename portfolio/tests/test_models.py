from decimal import Decimal

from django.test import TestCase

from portfolio.models import Account, AssetClass


class AssetClassTests(TestCase):
    def test_create_asset_class(self) -> None:
        """Test creating an asset class with valid data."""
        ac = AssetClass.objects.create(
            name="US Stocks",
            target_allocation_pct=Decimal("60.00"),
            expected_return=Decimal("7.5")
        )
        self.assertEqual(ac.name, "US Stocks")
        self.assertEqual(ac.target_allocation_pct, Decimal("60.00"))
        self.assertEqual(str(ac), "US Stocks (60.00%)")

class AccountTests(TestCase):
    def test_create_account(self) -> None:
        """Test creating an account with valid data."""
        account = Account.objects.create(
            name="My Roth IRA",
            account_type="ROTH_IRA",
            institution="Vanguard",
            tax_treatment="TAX_FREE"
        )
        self.assertEqual(account.name, "My Roth IRA")
        self.assertEqual(account.account_type, "ROTH_IRA")

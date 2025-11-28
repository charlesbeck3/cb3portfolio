from decimal import Decimal

from django.test import TestCase

from portfolio.models import Account, AssetClass, Holding, Security, TargetAllocation


class AssetClassTests(TestCase):
    def test_create_asset_class(self) -> None:
        """Test creating an asset class with valid data."""
        asset_class = AssetClass.objects.create(
            name="US Stocks",
            expected_return=Decimal("0.08")
        )
        self.assertEqual(asset_class.name, "US Stocks")
        self.assertEqual(str(asset_class), "US Stocks")

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

class SecurityTests(TestCase):
    def setUp(self) -> None:
        self.asset_class = AssetClass.objects.create(
            name="US Stocks"
        )

    def test_create_security(self) -> None:
        """Test creating a security with valid data."""
        security = Security.objects.create(
            ticker="VTI",
            name="Vanguard Total Stock Market ETF",
            asset_class=self.asset_class
        )
        self.assertEqual(security.ticker, "VTI")
        self.assertEqual(str(security), "VTI - Vanguard Total Stock Market ETF")

class HoldingTests(TestCase):
    def setUp(self) -> None:
        self.asset_class = AssetClass.objects.create(
            name="US Stocks"
        )
        self.account = Account.objects.create(
            name="Roth IRA",
            account_type="ROTH_IRA",
            institution="Vanguard",
            tax_treatment="TAX_FREE"
        )
        self.security = Security.objects.create(
            ticker="VTI",
            name="Vanguard Total Stock Market ETF",
            asset_class=self.asset_class
        )

    def test_create_holding(self) -> None:
        """Test creating a holding with valid data."""
        holding = Holding.objects.create(
            account=self.account,
            security=self.security,
            shares=Decimal("100.50"),
            cost_basis=Decimal("15000.00"),
            current_price=Decimal("160.00")
        )
        self.assertEqual(holding.shares, Decimal("100.50"))
        self.assertEqual(str(holding), "VTI in Roth IRA (100.50 shares)")

class TargetAllocationTests(TestCase):
    def setUp(self) -> None:
        self.asset_class = AssetClass.objects.create(
            name="US Stocks"
        )

    def test_create_target_allocation(self) -> None:
        """Test creating a target allocation."""
        target = TargetAllocation.objects.create(
            account_type="ROTH_IRA",
            asset_class=self.asset_class,
            target_pct=Decimal("40.00")
        )
        self.assertEqual(target.target_pct, Decimal("40.00"))
        self.assertEqual(str(target), "Roth IRA - US Stocks: 40.00%")

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from portfolio.models import (
    Account,
    AssetClass,
    Holding,
    RebalancingRecommendation,
    Security,
    TargetAllocation,
)


class AssetClassTests(TestCase):
    def test_create_asset_class(self) -> None:
        """Test creating an asset class."""
        ac = AssetClass.objects.create(
            name="US Stocks",
            expected_return=Decimal("0.08")
        )
        self.assertEqual(ac.name, "US Stocks")
        self.assertEqual(ac.expected_return, Decimal("0.08"))
        self.assertEqual(str(ac), "US Stocks")


class AccountTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="password")

    def test_create_account(self) -> None:
        """Test creating an account."""
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type="ROTH_IRA",
            institution="Vanguard",
            tax_treatment="TAX_FREE"
        )
        self.assertEqual(account.name, "Roth IRA")
        self.assertEqual(str(account), "Roth IRA (testuser)")


class SecurityTests(TestCase):
    def setUp(self) -> None:
        self.asset_class = AssetClass.objects.create(
            name="US Stocks"
        )

    def test_create_security(self) -> None:
        """Test creating a security."""
        security = Security.objects.create(
            ticker="VTI",
            name="Vanguard Total Stock Market ETF",
            asset_class=self.asset_class
        )
        self.assertEqual(security.ticker, "VTI")
        self.assertEqual(str(security), "VTI - Vanguard Total Stock Market ETF")


class HoldingTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="password")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks"
        )
        self.account = Account.objects.create(
            user=self.user,
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
        """Test creating a holding."""
        holding = Holding.objects.create(
            account=self.account,
            security=self.security,
            shares=Decimal("10.5000"),
            current_price=Decimal("210.00")
        )
        self.assertEqual(holding.shares, Decimal("10.5000"))
        self.assertEqual(str(holding), "VTI in Roth IRA (10.5000 shares)")


class TargetAllocationTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="password")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks"
        )

    def test_create_target_allocation(self) -> None:
        """Test creating a target allocation."""
        target = TargetAllocation.objects.create(
            user=self.user,
            account_type="ROTH_IRA",
            asset_class=self.asset_class,
            target_pct=Decimal("40.00")
        )
        self.assertEqual(target.target_pct, Decimal("40.00"))
        self.assertEqual(str(target), "Roth IRA - US Stocks: 40.00% (testuser)")

    def test_target_allocation_isolation(self) -> None:
        """Test that different users can have their own allocations."""
        # User 1 allocation
        TargetAllocation.objects.create(
            user=self.user,
            account_type="ROTH_IRA",
            asset_class=self.asset_class,
            target_pct=Decimal("40.00")
        )

        # User 2 allocation (same account type/asset class, different user)
        user2 = User.objects.create_user(username="otheruser", password="password")
        target2 = TargetAllocation.objects.create(
            user=user2,
            account_type="ROTH_IRA",
            asset_class=self.asset_class,
            target_pct=Decimal("60.00")
        )

        self.assertEqual(TargetAllocation.objects.count(), 2)
        self.assertEqual(target2.user.username, "otheruser")
        self.assertEqual(target2.target_pct, Decimal("60.00"))


class RebalancingRecommendationTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="password")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks"
        )
        self.account = Account.objects.create(
            user=self.user,
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

    def test_create_recommendation(self) -> None:
        """Test creating a rebalancing recommendation."""
        rec = RebalancingRecommendation.objects.create(
            account=self.account,
            security=self.security,
            action="BUY",
            shares=Decimal("10.00"),
            estimated_amount=Decimal("1600.00"),
            reason="Underweight"
        )
        self.assertEqual(rec.action, "BUY")
        self.assertEqual(str(rec), "BUY 10.00 VTI in Roth IRA")

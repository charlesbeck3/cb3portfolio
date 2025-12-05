from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import (
    Account,
    AssetCategory,
    AssetClass,
    Holding,
    Institution,
    RebalancingRecommendation,
    Security,
    TargetAllocation,
)

User = get_user_model()


class AssetClassTests(TestCase):
    def test_create_asset_class(self) -> None:
        """Test creating an asset class."""
        us_equities = AssetCategory.objects.get(code="US_EQUITIES")
        ac = AssetClass.objects.create(
            name="US Stocks",
            category=us_equities,
            expected_return=Decimal("0.08")
        )
        self.assertEqual(ac.name, "US Stocks")
        self.assertEqual(ac.expected_return, Decimal("0.08"))
        self.assertEqual(str(ac), "US Stocks")


class AccountTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="password")
        self.institution = Institution.objects.create(name="Vanguard")

    def test_create_account(self) -> None:
        """Test creating an account."""
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type="ROTH_IRA",
            institution=self.institution,
        )
        self.assertEqual(account.name, "Roth IRA")
        self.assertEqual(str(account), "Roth IRA (testuser)")

    def test_tax_treatment_property(self) -> None:
        """Test tax_treatment property derivation."""
        # Note: We need to provide required fields even if testing a property,
        # but since we are just instantiating the model (not saving), we can skip institution if not accessed.
        # However, to be safe and consistent, let's just use simple instantiation if possible,
        # or if we save, we need institution.
        # The original test instantiated without saving: roth = Account(account_type='ROTH_IRA')
        # This is fine as long as we don't save.

        roth = Account(account_type='ROTH_IRA')
        self.assertEqual(roth.tax_treatment, 'TAX_FREE')

        trad = Account(account_type='TRADITIONAL_IRA')
        self.assertEqual(trad.tax_treatment, 'TAX_DEFERRED')

        k401 = Account(account_type='401K')
        self.assertEqual(k401.tax_treatment, 'TAX_DEFERRED')

        taxable = Account(account_type='TAXABLE')
        self.assertEqual(taxable.tax_treatment, 'TAXABLE')


class SecurityTests(TestCase):
    def setUp(self) -> None:
        self.category = AssetCategory.objects.get(code="US_EQUITIES")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.category,
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
        self.institution = Institution.objects.create(name="Vanguard")
        self.category = AssetCategory.objects.get(code="US_EQUITIES")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.category,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type="ROTH_IRA",
            institution=self.institution,
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
        self.category = AssetCategory.objects.get(code="US_EQUITIES")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.category,
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
        self.institution = Institution.objects.create(name="Vanguard")
        self.category = AssetCategory.objects.get(code="US_EQUITIES")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.category,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type="ROTH_IRA",
            institution=self.institution,
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

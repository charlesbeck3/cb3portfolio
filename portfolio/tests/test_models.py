from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import (
    Account,
    AssetCategory,
    AssetClass,
    Holding,
    RebalancingRecommendation,
    Security,
    TargetAllocation,
)

from .base import PortfolioTestMixin

User = get_user_model()


class AssetClassTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()

    def test_create_asset_class(self) -> None:
        """Test creating an asset class."""
        # Use category created in mixin
        us_equities = self.cat_us_eq
        ac = AssetClass.objects.create(
            name="US Stocks",
            category=us_equities,
            expected_return=Decimal("0.08")
        )
        self.assertEqual(ac.name, "US Stocks")
        self.assertEqual(ac.expected_return, Decimal("0.08"))
        self.assertEqual(str(ac), "US Stocks")


class AccountTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        # self.institution = Institution.objects.create(name="Vanguard")

    def test_create_account(self) -> None:
        """Test creating an account."""
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
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

        roth = Account(account_type=self.type_roth)
        self.assertEqual(roth.tax_treatment, 'TAX_FREE')

        trad = Account(account_type=self.type_trad)
        self.assertEqual(trad.tax_treatment, 'TAX_DEFERRED')

        k401 = Account(account_type=self.type_401k)
        self.assertEqual(k401.tax_treatment, 'TAX_DEFERRED')

        taxable = Account(account_type=self.type_taxable)
        self.assertEqual(taxable.tax_treatment, 'TAXABLE')


class SecurityTests(TestCase, PortfolioTestMixin): # Added mixin just in case, though not strictly needed if not using AccountType
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
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


class HoldingTests(TestCase, PortfolioTestMixin): # Inherit from PortfolioTestMixin
    def setUp(self) -> None:
        self.setup_portfolio_data() # Call setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        # self.institution = Institution.objects.create(name="Vanguard") # Removed, as it's in mixin
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth, # Replaced string with model instance
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


class TargetAllocationTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )

    def test_create_target_allocation(self) -> None:
        """Test creating a target allocation."""
        target = TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class,
            target_pct=Decimal("40.00")
        )
        self.assertEqual(target.target_pct, Decimal("40.00"))
        # Using f-string to match new str logic if needed, but simple string also works provided type label is correct
        self.assertEqual(str(target), f"{self.user.username} - {self.type_roth.label} (Default) - {self.asset_class.name}: 40.00%")

    def test_target_allocation_isolation(self) -> None:
        """Test that different users can have their own allocations."""
        # User 1 allocation
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class,
            target_pct=Decimal("40.00")
        )

        # User 2 allocation (same account type/asset class, different user)
        user2 = User.objects.create_user(username="otheruser", password="password")
        target2 = TargetAllocation.objects.create(
            user=user2,
            account_type=self.type_roth,
            asset_class=self.asset_class,
            target_pct=Decimal("60.00")
        )

        self.assertEqual(TargetAllocation.objects.count(), 2)
        self.assertEqual(target2.user.username, "otheruser")
        self.assertEqual(target2.target_pct, Decimal("60.00"))


class RebalancingRecommendationTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
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

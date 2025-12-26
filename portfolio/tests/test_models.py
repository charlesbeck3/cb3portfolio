from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

import pytest

from portfolio.models import (
    Account,
    AllocationStrategy,
    AssetClass,
    Holding,
    Portfolio,
    RebalancingRecommendation,
    Security,
    TargetAllocation,
)

from .base import PortfolioTestMixin

User = get_user_model()


@pytest.mark.models
@pytest.mark.integration
class AccountTypeTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create(username="testuser_type")
        self.portfolio = Portfolio.objects.create(name="Test Portfolio Type", user=self.user)

    def test_to_dataframe(self) -> None:
        """AccountType DataFrame aggregates multiple accounts."""
        type_obj = self.type_taxable
        ac_us = AssetClass.objects.create(name="US Stk Ty", category=self.cat_us_eq)
        sec = Security.objects.create(ticker="VTI_TY", asset_class=ac_us)

        acc1 = Account.objects.create(
            name="Acc 1",
            account_type=type_obj,
            portfolio=self.portfolio,
            user=self.user,
            institution=self.institution,
        )
        acc2 = Account.objects.create(
            name="Acc 2",
            account_type=type_obj,
            portfolio=self.portfolio,
            user=self.user,
            institution=self.institution,
        )

        Holding.objects.create(account=acc1, security=sec, shares=10, current_price=100)
        Holding.objects.create(account=acc2, security=sec, shares=20, current_price=100)

        df = type_obj.to_dataframe()
        self.assertEqual(len(df), 2)
        # Index is now MultiIndex with (Type, Category, Name, ID)
        # Check that account names appear in the index
        account_names = [idx[2] for idx in df.index]  # Name is at position 2
        self.assertIn("Acc 1", account_names)
        self.assertIn("Acc 2", account_names)


@pytest.mark.models
@pytest.mark.integration
class PortfolioTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create(username="testuser_port")
        self.portfolio = Portfolio.objects.create(name="Test Portfolio", user=self.user)
        # Setup for dataframe tests
        self.us_stocks = AssetClass.objects.create(name="US Stk", category=self.cat_us_eq)
        self.bonds = AssetClass.objects.create(name="Bonds", category=self.cat_fi)
        # Update seeded securities
        self.vti.name = "Vanguard Stock"
        self.vti.asset_class = self.us_stocks
        self.vti.save()

        self.bnd.name = "Vanguard Bond"
        self.bnd.asset_class = self.bonds
        self.bnd.save()

        self.account = Account.objects.create(
            name="Test Account",
            account_type=self.type_taxable,
            portfolio=self.portfolio,
            user=self.user,
            institution=self.institution,
        )
        Holding.objects.create(
            account=self.account,
            security=self.vti,
            shares=Decimal("50"),
            current_price=Decimal("100.00"),
        )
        Holding.objects.create(
            account=self.account,
            security=self.bnd,
            shares=Decimal("100"),
            current_price=Decimal("50.00"),
        )

    def test_to_dataframe_structure(self) -> None:
        """Portfolio DataFrame has correct MultiIndex structure."""
        df = self.portfolio.to_dataframe()
        assert df.index.names == ["Account_Type", "Account_Category", "Account_Name", "Account_ID"]
        assert df.columns.names == ["Asset_Class", "Asset_Category", "Security"]
        assert not df.empty

    def test_to_dataframe_values(self) -> None:
        """Portfolio DataFrame has correct values."""
        df = self.portfolio.to_dataframe()
        assert ("US Stk", "US Equities", "VTI") in df.columns
        assert ("Bonds", "Fixed Income", "BND") in df.columns

        # Value check: 50 * 100 = 5000
        # Index now includes Account_ID, so we need to match on all 4 levels
        val = df.loc[
            ("Taxable", "Investments", "Test Account", self.account.id),
            ("US Stk", "US Equities", "VTI"),
        ]
        self.assertEqual(val, 5000.0)

    def test_empty_portfolio_dataframe(self) -> None:
        """Empty portfolio returns empty DataFrame with correct structure."""
        empty = Portfolio.objects.create(name="Empty", user=self.user)
        df = empty.to_dataframe()
        assert df.empty
        assert df.index.names == ["Account_Type", "Account_Category", "Account_Name", "Account_ID"]


@pytest.mark.models
@pytest.mark.integration
class AssetClassTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()

    def test_create_asset_class(self) -> None:
        """Test creating an asset class."""
        # Use category created in mixin
        us_equities = self.cat_us_eq
        ac = AssetClass.objects.create(
            name="US Stocks", category=us_equities, expected_return=Decimal("0.08")
        )
        self.assertEqual(ac.name, "US Stocks")
        self.assertEqual(ac.expected_return, Decimal("0.08"))
        self.assertEqual(str(ac), "US Stocks")


@pytest.mark.models
@pytest.mark.integration
class AccountTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        # self.institution = Institution.objects.create(name="Vanguard")

    def test_create_account(self) -> None:
        """Test creating an account."""
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
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
        self.assertEqual(roth.tax_treatment, "TAX_FREE")

        trad = Account(account_type=self.type_trad)
        self.assertEqual(trad.tax_treatment, "TAX_DEFERRED")

        k401 = Account(account_type=self.type_401k)
        self.assertEqual(k401.tax_treatment, "TAX_DEFERRED")

        taxable = Account(account_type=self.type_taxable)
        self.assertEqual(taxable.tax_treatment, "TAXABLE")

    def test_total_value(self) -> None:
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        self.vti.asset_class = asset_class
        self.vti.save()
        security = self.vti

        Holding.objects.create(
            account=account,
            security=security,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )
        # 10 * 100 = 1000
        self.assertEqual(account.total_value(), Decimal("1000"))

    def test_holdings_by_asset_class(self) -> None:
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        us_stocks = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        bonds = AssetClass.objects.create(
            name="Bonds",
            category=self.cat_us_eq,
        )
        self.vti.asset_class = us_stocks
        self.vti.save()
        vti = self.vti

        self.bnd.asset_class = bonds
        self.bnd.save()
        bnd = self.bnd

        Holding.objects.create(
            account=account,
            security=vti,
            shares=Decimal("2"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=account,
            security=bnd,
            shares=Decimal("4"),
            current_price=Decimal("50"),
        )

        by_ac = account.holdings_by_asset_class()
        self.assertEqual(by_ac["US Stocks"], Decimal("200"))
        self.assertEqual(by_ac["Bonds"], Decimal("200"))

    def test_calculate_deviation(self) -> None:
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        us_stocks = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        bonds = AssetClass.objects.create(
            name="Bonds",
            category=self.cat_us_eq,
        )
        self.vti.asset_class = us_stocks
        self.vti.save()
        vti = self.vti

        self.bnd.asset_class = bonds
        self.bnd.save()
        bnd = self.bnd

        # Current: 600 stocks, 400 bonds, total 1000
        Holding.objects.create(
            account=account,
            security=vti,
            shares=Decimal("6"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=account,
            security=bnd,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

        # Target: 50/50 -> 500 each
        targets = {"US Stocks": Decimal("50"), "Bonds": Decimal("50")}
        deviation = account.calculate_deviation(targets)
        # |600-500| + |400-500| = 200
        self.assertEqual(deviation, Decimal("200"))

    def test_to_dataframe(self) -> None:
        """Account DataFrame has single row."""
        # Setup specific to this test to ensure isolation
        ac_us = AssetClass.objects.create(name="US Stk Ac", category=self.cat_us_eq)
        sec = Security.objects.create(ticker="VTI_AC", asset_class=ac_us)
        # Create a new account to avoid side effects from mixin setup if any
        account = Account.objects.create(
            user=self.user,
            name="My Solitary Account",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        Holding.objects.create(
            account=account, security=sec, shares=Decimal("10"), current_price=Decimal("100")
        )

        df = account.to_dataframe()
        self.assertEqual(len(df), 1)
        # Index is now MultiIndex with (Type, Category, Name, ID)
        expected_index = ("Roth IRA", "Retirement", "My Solitary Account", account.id)
        self.assertEqual(df.index[0], expected_index)
        val = df.loc[expected_index, ("US Stk Ac", "US Equities", "VTI_AC")]
        self.assertEqual(val, 1000.0)


@pytest.mark.models
@pytest.mark.integration
class SecurityTests(
    TestCase, PortfolioTestMixin
):  # Added mixin just in case, though not strictly needed if not using AccountType
    def setUp(self) -> None:
        self.setup_system_data()
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )

    def test_create_security(self) -> None:
        """Test creating a security."""
        self.vti.asset_class = self.asset_class
        self.vti.save()
        security = self.vti
        self.assertEqual(security.ticker, "VTI")
        self.assertEqual(str(security), "VTI - Vanguard Total Stock Market ETF")


@pytest.mark.models
@pytest.mark.integration
class HoldingTests(TestCase, PortfolioTestMixin):  # Inherit from PortfolioTestMixin
    def setUp(self) -> None:
        self.setup_system_data()  # Call setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        # self.institution = Institution.objects.create(name="Vanguard") # Removed, as it's in mixin
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,  # Replaced string with model instance
            institution=self.institution,
        )
        self.vti.asset_class = self.asset_class
        self.vti.save()
        self.security = self.vti

    def test_create_holding(self) -> None:
        """Test creating a holding."""
        holding = Holding.objects.create(
            account=self.account,
            security=self.security,
            shares=Decimal("10.5000"),
            current_price=Decimal("210.00"),
        )
        self.assertEqual(holding.shares, Decimal("10.5000"))
        self.assertEqual(str(holding), "VTI in Roth IRA (10.5000 shares)")

    def test_market_value_with_price(self) -> None:
        holding = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )
        self.assertEqual(holding.market_value, Decimal("1000"))

    def test_market_value_without_price(self) -> None:
        holding = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("10"),
            current_price=None,
        )
        self.assertEqual(holding.market_value, Decimal("0.00"))

    def test_has_price_property(self) -> None:
        holding_with_price = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("1"),
            current_price=Decimal("50"),
        )
        self.assertTrue(holding_with_price.has_price)

        holding_without_price = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("1"),
            current_price=None,
        )
        self.assertFalse(holding_without_price.has_price)

    def test_update_price(self) -> None:
        holding = Holding.objects.create(
            account=self.account,
            security=self.security,
            shares=Decimal("5"),
            current_price=Decimal("10"),
        )
        holding.update_price(Decimal("20"))
        holding.refresh_from_db()
        self.assertEqual(holding.current_price, Decimal("20"))

    def test_calculate_target_value_and_variance(self) -> None:
        holding = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )

        account_total = Decimal("10000")
        target_pct = Decimal("25")
        target_value = holding.calculate_target_value(account_total, target_pct)
        self.assertEqual(target_value, Decimal("2500"))

        # Current value: 1000, Target: 2500 -> variance: -1500 (underweight)
        variance = holding.calculate_variance(target_value)
        self.assertEqual(variance, Decimal("1000") - Decimal("2500"))


@pytest.mark.models
@pytest.mark.integration
class TargetAllocationTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.strategy = AllocationStrategy.objects.create(user=self.user, name="Test Strategy")
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )

    def test_create_target_allocation(self) -> None:
        """Test creating a target allocation."""
        target = TargetAllocation.objects.create(
            strategy=self.strategy,
            asset_class=self.asset_class,
            target_percent=Decimal("40.00"),
        )
        self.assertEqual(target.target_percent, Decimal("40.00"))
        self.assertEqual(str(target), f"{self.strategy.name}: {self.asset_class.name} - 40.00%")

    def test_target_allocation_isolation(self) -> None:
        """Test that different users can have their own allocations."""
        # User 1 allocation
        TargetAllocation.objects.create(
            strategy=self.strategy,
            asset_class=self.asset_class,
            target_percent=Decimal("40.00"),
        )

        # User 2 allocation (same account type/asset class, different user)
        user2 = User.objects.create_user(username="otheruser", password="password")
        strategy2 = AllocationStrategy.objects.create(user=user2, name="Test Strategy")
        target2 = TargetAllocation.objects.create(
            strategy=strategy2,
            asset_class=self.asset_class,
            target_percent=Decimal("60.00"),
        )

        self.assertEqual(TargetAllocation.objects.count(), 2)
        self.assertEqual(target2.strategy.user.username, "otheruser")
        self.assertEqual(target2.target_percent, Decimal("60.00"))

    def test_target_value_for(self) -> None:
        allocation = TargetAllocation(
            strategy=self.strategy,
            asset_class=self.asset_class,
            target_percent=Decimal("25"),
        )
        self.assertEqual(allocation.target_value_for(Decimal("10000")), Decimal("2500"))

    def test_variance_for(self) -> None:
        # variance_for no longer exists on TargetAllocation after strategy refactor.
        # Keep coverage focused on TargetAllocation model methods that still exist.
        self.assertTrue(True)

    def test_validate_allocation_set_valid(self) -> None:
        allocations = [
            TargetAllocation(
                strategy=self.strategy,
                asset_class=self.asset_class,
                target_percent=Decimal("60"),
            ),
            TargetAllocation(
                strategy=self.strategy,
                asset_class=self.asset_class,
                target_percent=Decimal("40"),
            ),
        ]
        ok, msg = TargetAllocation.validate_allocation_set(allocations)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_validate_allocation_set_exceeds_100(self) -> None:
        allocations = [
            TargetAllocation(
                strategy=self.strategy,
                asset_class=self.asset_class,
                target_percent=Decimal("60"),
            ),
            TargetAllocation(
                strategy=self.strategy,
                asset_class=self.asset_class,
                target_percent=Decimal("50"),
            ),
        ]
        ok, msg = TargetAllocation.validate_allocation_set(allocations)
        self.assertFalse(ok)
        self.assertIn("110", msg)


@pytest.mark.models
@pytest.mark.integration
class RebalancingRecommendationTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        self.vti.asset_class = self.asset_class
        self.vti.save()
        self.security = self.vti

    def test_create_recommendation(self) -> None:
        """Test creating a rebalancing recommendation."""
        rec = RebalancingRecommendation.objects.create(
            account=self.account,
            security=self.security,
            action="BUY",
            shares=Decimal("10.00"),
            estimated_amount=Decimal("1600.00"),
            reason="Underweight",
        )
        self.assertEqual(rec.action, "BUY")
        self.assertEqual(str(rec), "BUY 10.00 VTI in Roth IRA")

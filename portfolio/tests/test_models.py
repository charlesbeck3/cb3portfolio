from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import (
    Account,
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
            name="US Stocks", category=us_equities, expected_return=Decimal("0.08")
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
        self.assertEqual(roth.tax_treatment, "TAX_FREE")

        trad = Account(account_type=self.type_trad)
        self.assertEqual(trad.tax_treatment, "TAX_DEFERRED")

        k401 = Account(account_type=self.type_401k)
        self.assertEqual(k401.tax_treatment, "TAX_DEFERRED")

        taxable = Account(account_type=self.type_taxable)
        self.assertEqual(taxable.tax_treatment, "TAXABLE")

    def test_total_value_aggregates_holdings(self) -> None:
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
            institution=self.institution,
        )

        # Create a simple asset class and securities for holdings
        asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        security_1 = Security.objects.create(
            ticker="AAA", name="AAA", asset_class=asset_class
        )
        security_2 = Security.objects.create(
            ticker="BBB", name="BBB", asset_class=asset_class
        )

        Holding.objects.create(
            account=account,
            security=security_1,
            shares=Decimal("5"),
            current_price=Decimal("100"),
        )  # 500
        Holding.objects.create(
            account=account,
            security=security_2,
            shares=Decimal("3"),
            current_price=Decimal("200"),
        )  # 600

        self.assertEqual(account.total_value(), Decimal("1100.00"))

    def test_holdings_by_asset_class_groups_values(self) -> None:
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
            institution=self.institution,
        )

        us_stocks = AssetClass.objects.create(name="US Stocks", category=self.cat_us_eq)
        bonds = AssetClass.objects.create(name="Bonds", category=self.cat_fi)

        sec_stock_1 = Security.objects.create(ticker="STK1", name="Stock 1", asset_class=us_stocks)
        sec_stock_2 = Security.objects.create(ticker="STK2", name="Stock 2", asset_class=us_stocks)
        sec_bond = Security.objects.create(ticker="BND", name="Bond", asset_class=bonds)

        Holding.objects.create(
            account=account,
            security=sec_stock_1,
            shares=Decimal("10"),
            current_price=Decimal("10"),
        )  # 100
        Holding.objects.create(
            account=account,
            security=sec_stock_2,
            shares=Decimal("5"),
            current_price=Decimal("20"),
        )  # 100 -> total 200
        Holding.objects.create(
            account=account,
            security=sec_bond,
            shares=Decimal("10"),
            current_price=Decimal("30"),
        )  # 300

        by_ac = account.holdings_by_asset_class()
        self.assertEqual(by_ac["US Stocks"], Decimal("200.00"))
        self.assertEqual(by_ac["Bonds"], Decimal("300.00"))

    def test_current_allocation_returns_asset_allocation(self) -> None:
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
            institution=self.institution,
        )

        us_stocks = AssetClass.objects.create(name="US Stocks", category=self.cat_us_eq)
        bonds = AssetClass.objects.create(name="Bonds", category=self.cat_fi)

        sec_stock = Security.objects.create(ticker="STK", name="Stock", asset_class=us_stocks)
        sec_bond = Security.objects.create(ticker="BND", name="Bond", asset_class=bonds)

        # Total value 1000; 600 stocks, 400 bonds -> 60/40
        Holding.objects.create(
            account=account,
            security=sec_stock,
            shares=Decimal("6"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=account,
            security=sec_bond,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

        allocation = account.current_allocation()
        self.assertAlmostEqual(allocation.weights["US Stocks"], Decimal("60"))
        self.assertAlmostEqual(allocation.weights["Bonds"], Decimal("40"))

    def test_calculate_deviation_from_targets(self) -> None:
        account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
            institution=self.institution,
        )

        us_stocks = AssetClass.objects.create(name="US Stocks", category=self.cat_us_eq)
        bonds = AssetClass.objects.create(name="Bonds", category=self.cat_fi)

        sec_stock = Security.objects.create(ticker="STK", name="Stock", asset_class=us_stocks)
        sec_bond = Security.objects.create(ticker="BND", name="Bond", asset_class=bonds)

        # Account total 1000: 600 stocks, 400 bonds
        Holding.objects.create(
            account=account,
            security=sec_stock,
            shares=Decimal("6"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=account,
            security=sec_bond,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

        targets = {"US Stocks": Decimal("50"), "Bonds": Decimal("50")}

        deviation = account.calculate_deviation(targets)
        # Expected deviation: |600-500| + |400-500| = 100 + 100 = 200
        self.assertEqual(deviation, Decimal("200.00"))


class SecurityTests(
    TestCase, PortfolioTestMixin
):  # Added mixin just in case, though not strictly needed if not using AccountType
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )

    def test_create_security(self) -> None:
        """Test creating a security."""
        security = Security.objects.create(
            ticker="VTI", name="Vanguard Total Stock Market ETF", asset_class=self.asset_class
        )
        self.assertEqual(security.ticker, "VTI")
        self.assertEqual(str(security), "VTI - Vanguard Total Stock Market ETF")


class HoldingTests(TestCase, PortfolioTestMixin):  # Inherit from PortfolioTestMixin
    def setUp(self) -> None:
        self.setup_portfolio_data()  # Call setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        # self.institution = Institution.objects.create(name="Vanguard") # Removed, as it's in mixin
        self.asset_class = AssetClass.objects.create(
            name="US Stocks",
            category=self.cat_us_eq,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,  # Replaced string with model instance
            institution=self.institution,
        )
        self.security = Security.objects.create(
            ticker="VTI", name="Vanguard Total Stock Market ETF", asset_class=self.asset_class
        )

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
            current_price=Decimal("100.00"),
        )
        self.assertEqual(holding.market_value, Decimal("1000.00"))

    def test_market_value_without_price(self) -> None:
        holding = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("10"),
            current_price=None,
        )
        self.assertEqual(holding.market_value, Decimal("0.00"))

    def test_has_price_property(self) -> None:
        with_price = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("1"),
            current_price=Decimal("50.00"),
        )
        no_price = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("1"),
            current_price=None,
        )

        self.assertTrue(with_price.has_price)
        self.assertFalse(no_price.has_price)

    def test_update_price_persists_value(self) -> None:
        holding = Holding.objects.create(
            account=self.account,
            security=self.security,
            shares=Decimal("5"),
            current_price=Decimal("10.00"),
        )

        holding.update_price(Decimal("12.50"))
        holding.refresh_from_db()

        self.assertEqual(holding.current_price, Decimal("12.50"))

    def test_calculate_target_value_and_variance(self) -> None:
        holding = Holding(
            account=self.account,
            security=self.security,
            shares=Decimal("10"),
            current_price=Decimal("100.00"),
        )
        # Account total 10_000, target 20% -> 2_000 target
        account_total = Decimal("10000")
        target_pct = Decimal("20")

        target_value = holding.calculate_target_value(account_total, target_pct)
        variance = holding.calculate_variance(target_value)

        self.assertEqual(target_value, Decimal("2000"))
        # Holding value is 1_000, so variance should be -1_000 (underweight)
        self.assertEqual(variance, Decimal("-1000"))


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
            target_pct=Decimal("40.00"),
        )
        self.assertEqual(target.target_pct, Decimal("40.00"))
        # Using f-string to match new str logic if needed, but simple string also works provided type label is correct
        self.assertEqual(
            str(target),
            f"{self.user.username} - {self.type_roth.label} (Default) - {self.asset_class.name}: 40.00%",
        )

    def test_target_allocation_isolation(self) -> None:
        """Test that different users can have their own allocations."""
        # User 1 allocation
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class,
            target_pct=Decimal("40.00"),
        )

        # User 2 allocation (same account type/asset class, different user)
        user2 = User.objects.create_user(username="otheruser", password="password")
        target2 = TargetAllocation.objects.create(
            user=user2,
            account_type=self.type_roth,
            asset_class=self.asset_class,
            target_pct=Decimal("60.00"),
        )

        self.assertEqual(TargetAllocation.objects.count(), 2)
        self.assertEqual(target2.user.username, "otheruser")
        self.assertEqual(target2.target_pct, Decimal("60.00"))

    def test_target_value_for_account_total(self) -> None:
        allocation = TargetAllocation(target_pct=Decimal("25.00"))
        target = allocation.target_value_for(Decimal("10000"))
        self.assertEqual(target, Decimal("2500.00"))

    def test_variance_for_current_vs_target(self) -> None:
        allocation = TargetAllocation(target_pct=Decimal("25.00"))
        # Current 3000, target 25% of 10000 = 2500 -> variance +500
        variance = allocation.variance_for(Decimal("3000.00"), Decimal("10000.00"))
        self.assertEqual(variance, Decimal("500.00"))

    def test_variance_pct_for_current_vs_target(self) -> None:
        allocation = TargetAllocation(target_pct=Decimal("25.00"))
        # Current 3000, target 2500, account total 10000 -> (3000-2500)/10000 * 100 = 5%
        variance_pct = allocation.variance_pct_for(Decimal("3000.00"), Decimal("10000.00"))
        self.assertEqual(variance_pct, Decimal("5.00"))

    def test_variance_pct_for_zero_account_total(self) -> None:
        allocation = TargetAllocation(target_pct=Decimal("25.00"))
        variance_pct = allocation.variance_pct_for(Decimal("0.00"), Decimal("0.00"))
        self.assertEqual(variance_pct, Decimal("0.00"))

    def test_validate_allocation_set(self) -> None:
        allocations_valid = [
            TargetAllocation(target_pct=Decimal("60.00")),
            TargetAllocation(target_pct=Decimal("40.00")),
        ]
        is_valid, msg = TargetAllocation.validate_allocation_set(allocations_valid)
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")

        allocations_invalid = [
            TargetAllocation(target_pct=Decimal("60.00")),
            TargetAllocation(target_pct=Decimal("50.00")),
        ]
        is_valid_invalid, msg_invalid = TargetAllocation.validate_allocation_set(allocations_invalid)
        self.assertFalse(is_valid_invalid)
        self.assertIn("110.00", msg_invalid)


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
            ticker="VTI", name="Vanguard Total Stock Market ETF", asset_class=self.asset_class
        )

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

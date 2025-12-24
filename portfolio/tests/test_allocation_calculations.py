from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import (
    Account,
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Holding,
    Institution,
    Portfolio,
    Security,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine

User = get_user_model()


class AllocationCalculationEngineTotalsTests(TestCase):
    """Test the account totals extraction in AllocationCalculationEngine."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser")
        self.portfolio = Portfolio.objects.create(user=self.user, name="Test Portfolio")

        self.category = AssetClassCategory.objects.create(code="EQUITY", label="Equities")
        self.asset_class = AssetClass.objects.create(name="US Stocks", category=self.category)

        self.group = AccountGroup.objects.create(name="Brokerage")
        self.account_type = AccountType.objects.create(
            code="TAXABLE", label="Taxable", group=self.group, tax_treatment="TAXABLE"
        )
        self.institution = Institution.objects.create(name="Test Inst")

        self.security = Security.objects.create(
            ticker="TEST", name="Test Security", asset_class=self.asset_class
        )

    def test_get_account_totals_simple(self) -> None:
        """Test get_account_totals returns correct values."""
        account = Account.objects.create(
            user=self.user,
            name="Test Account",
            portfolio=self.portfolio,
            account_type=self.account_type,
            institution=self.institution,
        )

        # Create holding: 10 shares @ $100 = $1000
        Holding.objects.create(
            account=account,
            security=self.security,
            shares=Decimal("10"),
            current_price=Decimal("100.00"),
        )

        engine = AllocationCalculationEngine()
        totals = engine.get_account_totals(self.user)

        self.assertEqual(totals[account.id], Decimal("1000.00"))

    def test_get_account_totals_multiple_accounts(self) -> None:
        """Test get_account_totals with multiple accounts."""
        account1 = Account.objects.create(
            user=self.user,
            name="Account 1",
            portfolio=self.portfolio,
            account_type=self.account_type,
            institution=self.institution,
        )

        account2 = Account.objects.create(
            user=self.user,
            name="Account 2",
            portfolio=self.portfolio,
            account_type=self.account_type,
            institution=self.institution,
        )

        # Account 1: $1000
        Holding.objects.create(
            account=account1,
            security=self.security,
            shares=Decimal("10"),
            current_price=Decimal("100.00"),
        )

        # Account 2: $2500
        Holding.objects.create(
            account=account2,
            security=self.security,
            shares=Decimal("25"),
            current_price=Decimal("100.00"),
        )

        engine = AllocationCalculationEngine()
        totals = engine.get_account_totals(self.user)

        self.assertEqual(totals[account1.id], Decimal("1000.00"))
        self.assertEqual(totals[account2.id], Decimal("2500.00"))
        self.assertEqual(len(totals), 2)

    def test_get_account_totals_empty_portfolio(self) -> None:
        """Test get_account_totals with no holdings."""
        engine = AllocationCalculationEngine()
        totals = engine.get_account_totals(self.user)

        self.assertEqual(totals, {})

    def test_get_portfolio_total(self) -> None:
        """Test get_portfolio_total sums all accounts."""
        account1 = Account.objects.create(
            user=self.user,
            name="Account 1",
            portfolio=self.portfolio,
            account_type=self.account_type,
            institution=self.institution,
        )

        account2 = Account.objects.create(
            user=self.user,
            name="Account 2",
            portfolio=self.portfolio,
            account_type=self.account_type,
            institution=self.institution,
        )

        Holding.objects.create(
            account=account1,
            security=self.security,
            shares=Decimal("10"),
            current_price=Decimal("100.00"),
        )

        Holding.objects.create(
            account=account2,
            security=self.security,
            shares=Decimal("25"),
            current_price=Decimal("100.00"),
        )

        engine = AllocationCalculationEngine()
        total = engine.get_portfolio_total(self.user)

        self.assertEqual(total, Decimal("3500.00"))

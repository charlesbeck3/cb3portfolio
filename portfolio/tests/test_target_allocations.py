import unittest.mock
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    AssetClass,
    AssetClassCategory,
    Holding,
    Security,
    TargetAllocation,
)

from .base import PortfolioTestMixin

User = get_user_model()


class TargetAllocationViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.client.force_login(self.user)

        # Setup Assets
        self.cat_eq, _ = AssetClassCategory.objects.get_or_create(
            code="EQUITIES", defaults={"label": "Equities", "sort_order": 1}
        )
        self.ac_us, _ = AssetClass.objects.get_or_create(
            name="US Stocks", defaults={"category": self.cat_eq}
        )
        self.sec_vti, _ = Security.objects.get_or_create(
            ticker="VTI", defaults={"name": "VTI", "asset_class": self.ac_us}
        )

        self.cat_cash, _ = AssetClassCategory.objects.get_or_create(
            code="CASH", defaults={"label": "Cash", "sort_order": 10}
        )
        self.ac_cash, _ = AssetClass.objects.get_or_create(
            name="Cash", defaults={"category": self.cat_cash}
        )
        self.sec_cash, _ = Security.objects.get_or_create(
            ticker="CASH", defaults={"name": "Cash", "asset_class": self.ac_cash}
        )

        # Setup Accounts
        self.acc_roth = Account.objects.create(
            user=self.user,
            name="My Roth",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        self.acc_tax = Account.objects.create(
            user=self.user,
            name="My Taxable",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )

        # Setup Holdings
        Holding.objects.create(
            account=self.acc_roth, security=self.sec_vti, shares=60, current_price=100
        )
        Holding.objects.create(
            account=self.acc_tax, security=self.sec_vti, shares=20, current_price=100
        )
        Holding.objects.create(
            account=self.acc_tax, security=self.sec_cash, shares=2000, current_price=1
        )

        # Setup Strategies
        self.strategy_conservative = AllocationStrategy.objects.create(
            user=self.user, name="Conservative"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_conservative, asset_class=self.ac_us, target_percent=40
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_conservative, asset_class=self.ac_cash, target_percent=60
        )

        self.strategy_aggressive = AllocationStrategy.objects.create(
            user=self.user, name="Aggressive"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_aggressive, asset_class=self.ac_us, target_percent=90
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_aggressive, asset_class=self.ac_cash, target_percent=10
        )

    def test_initial_calculation(self) -> None:
        """Verify context data includes strategies and totals."""
        url = reverse("portfolio:target_allocations")

        with unittest.mock.patch("portfolio.services.MarketDataService.get_prices") as mock_prices:
            mock_prices.return_value = {"VTI": Decimal("100.00"), "CASH": Decimal("1.00")}
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        context = response.context

        # Verify strategies are in context
        self.assertIn("strategies", context)
        self.assertEqual(len(context["strategies"]), 2)

        # Verify portfolio value
        self.assertEqual(context["portfolio_total_value"], Decimal("10000.00"))

    def test_save_account_type_allocation(self) -> None:
        """Verify assigning a strategy to an Account Type."""
        url = reverse("portfolio:target_allocations")

        # Assign Aggressive to ROTH_IRA
        data = {
            f"strategy_at_{self.type_roth.id}": str(self.strategy_aggressive.id),
            # Leave Taxable empty (no change/clear)
            f"strategy_at_{self.type_taxable.id}": "",
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        # Verify DB
        assignment = AccountTypeStrategyAssignment.objects.get(
            user=self.user,
            account_type=self.type_roth,
        )
        self.assertEqual(assignment.allocation_strategy, self.strategy_aggressive)

        # Verify Taxable has no assignment
        self.assertFalse(AccountTypeStrategyAssignment.objects.filter(
            user=self.user,
            account_type=self.type_taxable
        ).exists())

    def test_save_account_override_allocation(self) -> None:
        """Verify assigning an override strategy to a specific Account."""
        url = reverse("portfolio:target_allocations")

        # Assign Conservative to My Roth (override)
        data = {
            f"strategy_acc_{self.acc_roth.id}": str(self.strategy_conservative.id),
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        # Verify DB
        self.acc_roth.refresh_from_db()
        self.assertEqual(self.acc_roth.allocation_strategy, self.strategy_conservative)

    def test_clear_allocation(self) -> None:
        """Verify clearing a strategy assignment."""
        # Setup initial assignment
        AccountTypeStrategyAssignment.objects.create(
            user=self.user,
            account_type=self.type_roth,
            allocation_strategy=self.strategy_aggressive
        )

        url = reverse("portfolio:target_allocations")

        # Post empty string for Roth
        data = {
            f"strategy_at_{self.type_roth.id}": "",
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        # Verify assignment is gone
        self.assertFalse(AccountTypeStrategyAssignment.objects.filter(
            user=self.user,
            account_type=self.type_roth
        ).exists())

    def test_redundant_subtotals(self) -> None:
        """Verify redundant subtotal rows are suppressed/shown correctly."""
        # Add another category with 1 asset
        bond_cat = AssetClassCategory.objects.create(
            label="Fixed Income", code="BONDS", sort_order=2
        )
        AssetClass.objects.create(name="US Bond", category=bond_cat)

        # Ensure Equities has multiple assets (US Stocks + Intl Stocks)
        self.cat_eq.label = "Stocks"
        self.cat_eq.save()
        AssetClass.objects.create(name="Intl Stock", category=self.cat_eq)

        with unittest.mock.patch("portfolio.services.MarketDataService.get_prices") as mock_prices:
            mock_prices.return_value = {}
            response = self.client.get(reverse("portfolio:target_allocations"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # Single asset category -> No subtotal
        self.assertNotIn("Fixed Income Total", content)

        # Multi asset category -> Has subtotal
        self.assertIn("Stocks Total", content)

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    Holding,
    TargetAllocation,
)

from .base import PortfolioTestMixin

User = get_user_model()


class DashboardViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.client.force_login(self.user)

        # Create an account for Roth only.
        # The mixin creates 4 types: Roth, Trad, Taxable, 401k.
        Account.objects.create(
            user=self.user,
            name="My Roth",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )

    def test_account_types_context_filtering(self) -> None:
        """
        Verify that only account types with associated accounts for the user
        are included in the context.
        """
        url = reverse("portfolio:dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Extract account_types from context
        # It is a list of AccountType objects
        account_types = response.context["account_types"]
        # Convert to list of codes for easy checking
        codes = [item.code for item in account_types]  # item is AccountType object

        self.assertIn("ROTH_IRA", codes)
        self.assertNotIn("TRADITIONAL_IRA", codes)
        self.assertNotIn("TAXABLE", codes)

    def test_redundant_totals(self) -> None:
        """
        Verify that redundant total rows are suppressed:
        1. Category Total hidden if Category has only 1 Asset Class.
        2. Group Total hidden if Group has only 1 Asset Class (total).
        """
        # --- Setup Data ---

        # 1. Single Asset Group (simulating Cash)
        # Seeded data already has Category 'Cash' -> Asset Class 'Cash' -> Security 'CASH'
        sec_cash = self.sec_cash

        # Create Holding in a Deposit Account
        acc_dep = Account.objects.create(
            user=self.user,
            name="My Cash",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )
        Holding.objects.create(account=acc_dep, security=sec_cash, shares=100, current_price=1)

        # 2. Multi-Asset Group
        # Category 'Equities' (self.category_equities) has parent None, but US Equities has parent Equities.
        # Seeded US Equities (self.asset_class_us_equities) -> Cat 'US_EQUITIES' -> Parent 'EQUITIES'.
        # Seeded Intl Dev Equities (self.asset_class_intl_developed) -> Cat 'INTERNATIONAL_EQUITIES' -> Parent 'EQUITIES'.

        # Use seeded objects for group comparison
        sec_us = self.vti
        Holding.objects.create(account=acc_dep, security=sec_us, shares=10, current_price=100)

        sec_intl = self.vea
        Holding.objects.create(account=acc_dep, security=sec_intl, shares=10, current_price=50)

        # --- Execute ---
        response = self.client.get(reverse("portfolio:dashboard"))
        content = response.content.decode("utf-8")

        # --- Assertions ---

        # 1. Cash Scenario (Single Asset Class in Group 'CASH')
        # Asset Class 'Cash' should be present
        self.assertIn("Cash", content)
        # Category Total 'Cash Total' should NOT be present (Category has 1 AC)
        # Group Total 'Cash Total' should NOT be present (Group has 1 AC)
        # Note: If label is "Cash", total row is "Cash Total".
        self.assertNotIn("Cash Total", content, "Redundant Total row for Cash should be hidden.")

        # 2. Equities Scenario (Multi Asset Class in Group 'EQUITIES')
        # Category 'US Equities' has 1 Asset Class -> 'US Equities Total' should be HIDDEN
        self.assertNotIn(
            "US Equities Total",
            content,
            "Redundant Category Total for US Equities should be hidden.",
        )

        # Parent Category 'Equities' has 2 Asset Classes (US Equities + Intl Dev Equities) -> Total SHOWN
        self.assertIn("Equities Total", content, "Group Total for Equities should be shown.")

    def test_dashboard_calculated_values(self) -> None:
        """
        Verify that dashboard tables contain calculated values for:
        1. Category Subtotals
        2. Group Totals
        3. Grand Totals
        4. Cash Row
        """
        # Setup Data
        # Group "Investments"
        # Use seeded objects
        ac_us = self.asset_class_us_equities
        sec_us = self.vti

        # Account
        acc_tax = Account.objects.create(
            user=self.user,
            name="My Taxable",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )

        # Holding: $1000 VTI
        Holding.objects.create(account=acc_tax, security=sec_us, shares=10, current_price=100)

        # Targets: Set US Equities to 50% for Taxable
        strategy, _ = AllocationStrategy.objects.update_or_create(
            user=self.user,
            name=f"{acc_tax.account_type.label} Strategy",
            defaults={"description": f"Default strategy for {acc_tax.account_type.label}"},
        )
        strategy.target_allocations.all().delete()
        TargetAllocation.objects.create(
            strategy=strategy, asset_class=ac_us, target_percent=Decimal("50.00")
        )
        AccountTypeStrategyAssignment.objects.update_or_create(
            user=self.user,
            account_type=acc_tax.account_type,
            defaults={"allocation_strategy": strategy},
        )

        # Force pricing update (mock or ensure service called)
        # Service is called in view.
        # But we need MarketDataService to return stable prices if view calls it.
        # Or just trust DB if logic skips update? Service usually calls update_prices.
        # Let's mock it to be safe.
        from unittest.mock import patch

        with patch("portfolio.services.MarketDataService.get_prices") as mock_prices:
            mock_prices.return_value = {"VTI": Decimal("100.00")}
            response = self.client.get(reverse("portfolio:dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # Calculate Expected Values
        # Total Value: $1000
        # Target US Stocks: 50% of $1000 = $500
        # Variance US Stocks: $1000 - $500 = $500

        # We look for these formatted strings in the HTML.
        # Note: formatting might include commas, parentheses for negative. $1,000.00 or 1,000 etc.
        # The template uses accounting_amount:0 or similar.
        # Assuming accounting_amount:0 formats as "1,000" (int) or "1,000.00"?
        # Current logic usually is `|accounting_amount:0` -> check `portfolio_extras`.
        # Assuming it produces "1,000" or "$1,000".
        # Let's check for "500" and "1,000" in relevant context if possible, or just presence.

        # Specific Checks:
        # 1. Category Subtotal for 'Equities': Should match Asset Class total since only 1 AC.
        # Wait, if only 1 AC, Subtotal is HIDDEN? Yes (test_redundant_totals).
        # So we need 2 ACs to test Subtotal Row values.
        ac_intl = self.asset_class_intl_developed
        sec_intl = self.vxus

        Holding.objects.create(account=acc_tax, security=sec_intl, shares=10, current_price=50)
        # Add target for Intl: 40%
        TargetAllocation.objects.create(
            strategy=strategy, asset_class=ac_intl, target_percent=Decimal("40.00")
        )

        # New Totals:
        # VTI: $1000. Target (50% of $1500? No, 50% of Account Total).
        # Account Total = $1000 + $500 = $1500.
        # US Target: 50% * 1500 = $750. Var: 1000 - 750 = 250.
        # Intl Target: 40% * 1500 = $600. Var: 500 - 600 = -100.

        # Category Total (Equities):
        # Current: 1500
        # Target: 750 + 600 = 1350 (90%)
        # Variance: 1500 - 1350 = 150.

        # Re-fetch with new data
        with patch("portfolio.services.MarketDataService.get_prices") as mock_prices:
            mock_prices.return_value = {"VTI": Decimal("100.00"), "VXUS": Decimal("50.00")}
            response = self.client.get(reverse("portfolio:dashboard"))
        content = response.content.decode("utf-8")

        # Search for Strings
        # formatting helper:
        def fmt(val: int | float | Decimal) -> str:
            return f"{val:,.0f}"  # Simple int calc

        # US Row
        self.assertIn("1,000", content)  # Current
        self.assertIn("750", content)  # Target
        self.assertIn("$250", content)  # Variance (now with $)

        # Intl Row
        self.assertIn("500", content)  # Current
        self.assertIn("600", content)  # Target
        self.assertIn("($100)", content)  # Variance (negative in parens with $)

        # Category Subtotal 'Equities Total'
        self.assertIn("Equities Total", content)
        self.assertIn("1,500", content)  # Current
        self.assertIn("1,350", content)  # Target
        self.assertIn("$150", content)  # Variance (now with $)

        # Grand Total Row
        # "Total" label
        self.assertIn("Total", content)
        # Should match sums
        self.assertIn("1,500", content)  # Grand Current
        self.assertIn("1,350", content)  # Grand Target
        self.assertIn("$150", content)  # Grand Variance (now with $)


class HoldingsViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.client.force_login(self.user)

        self.account = Account.objects.create(
            user=self.user,
            name="My Roth",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )

    def test_holdings_view(self) -> None:
        url = reverse("portfolio:holdings")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portfolio/holdings.html")
        self.assertIn("holdings_rows", response.context)
        self.assertIn("sidebar_data", response.context)
        # Account should not be in context
        self.assertNotIn("account", response.context)

    def test_holdings_view_with_account(self) -> None:
        url = reverse("portfolio:account_holdings", args=[self.account.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portfolio/holdings.html")
        self.assertIn("account", response.context)
        self.assertEqual(response.context["account"], self.account)

    def test_holdings_view_invalid_account(self) -> None:
        # Should suppress DoesNotExist
        url = reverse("portfolio:account_holdings", args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("account", response.context)

    def test_target_allocations_has_sidebar_context(self) -> None:
        """Test that Target Allocations view includes sidebar data."""
        url = reverse("portfolio:target_allocations")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("sidebar_data", response.context, "sidebar_data missing from context")
        self.assertIsNotNone(response.context["sidebar_data"]["groups"], "Sidebar groups missing")
        self.assertGreater(
            len(response.context["sidebar_data"]["groups"]), 0, "Sidebar should have groups"
        )

    def test_dashboard_has_sidebar_context(self) -> None:
        """Test that Dashboard view includes sidebar data."""
        url = reverse("portfolio:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("sidebar_data", response.context)

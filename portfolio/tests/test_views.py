from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import (
    Account,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Holding,
    Security,
    TargetAllocation,
)

from .base import PortfolioTestMixin

User = get_user_model()


class DashboardViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.force_login(self.user)

        # Create an account for Roth only.
        # The mixin creates 4 types: Roth, Trad, Taxable, 401k.
        Account.objects.create(
            user=self.user,
            name="My Roth",
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
        # Group 'Deposit Accounts' (self.group_dep) created in mixin.
        # Create Category 'Cash' -> 1 Asset Class 'Cash' -> 1 Security 'CASH'
        cat_cash, _ = AssetClassCategory.objects.get_or_create(
            code="CASH", defaults={"label": "Cash", "sort_order": 10}
        )
        ac_cash, _ = AssetClass.objects.get_or_create(
            name="Cash", defaults={"category": cat_cash, "expected_return": 0}
        )
        sec_cash, _ = Security.objects.get_or_create(
            ticker="CASH", defaults={"name": "Cash Holding", "asset_class": ac_cash}
        )

        # Create Holding in a Deposit Account
        acc_dep = Account.objects.create(
            user=self.user,
            name="My Cash",
            account_type=AccountType.objects.get(
                code="TAXABLE"
            ),  # Using TAXABLE for simplicity, technically could be DEPOSIT
            institution=self.institution,
        )
        Holding.objects.create(account=acc_dep, security=sec_cash, shares=100, current_price=1)

        # 2. Multi-Asset Group
        # Group 'Investments' (self.group_inv).
        # Category 'Equities' -> 2 Asset Classes 'US Stocks', 'Intl Stocks'
        cat_eq, _ = AssetClassCategory.objects.get_or_create(
            code="EQUITIES", defaults={"label": "Equities", "sort_order": 1}
        )
        # Link category to group? The link is via AssetClassCategory.parent??
        # Logic in services.py: group = category.parent or category.
        # But wait, Group is AccountGroup, Category is AssetClassCategory.
        # services.py maps: group_code = category.parent or category.code
        # And summary.groups keys are these codes.
        # BUT AccountGroup logic in get_account_summary is different from get_holdings_summary?
        # Re-read services.py:
        # _build_category_maps loops categories. group = category.parent or category.
        # This means "Group" in the dashboard holdings table is actually the Parent Category (if exists) or the Category itself.
        # It is NOT AccountGroup.

        # So "Cash" scenario: Category 'Cash' (parent=None). Group Code = 'CASH'.
        # It has 1 Asset Class.
        # So Group 'CASH' has 1 Asset Class.

        # "Investments" scenario?
        # If we have US Equities (parent=Equities) and Intl Equities (parent=Equities).
        # Group Code = 'Equities'.
        # Group 'Equities' has 2 Categories (US, Intl) -> Multiple Asset Classes (>=2).
        # So Group Total for 'Equities' should be SHOWN.

        # Let's create 'Equities' Parent Category
        # Note: code='EQUITIES' might already exist from earlier lines or mixin. Ensure label is set.
        cat_parent_eq, _ = AssetClassCategory.objects.get_or_create(
            code="EQUITIES", defaults={"label": "Equities Parent", "sort_order": 1}
        )
        cat_parent_eq.label = "Equities Parent"
        cat_parent_eq.save()

        # Sub-category 1: US Equities
        # Force parent assignment as it might exist from mixin without parent
        cat_us, _ = AssetClassCategory.objects.get_or_create(
            code="US_EQ",
            defaults={"label": "US Equities", "parent": cat_parent_eq, "sort_order": 1},
        )
        cat_us.parent = cat_parent_eq
        cat_us.save()

        ac_us, _ = AssetClass.objects.get_or_create(
            name="US Stocks", defaults={"category": cat_us, "expected_return": 0.1}
        )
        sec_us, _ = Security.objects.get_or_create(
            ticker="VTI", defaults={"name": "VTI", "asset_class": ac_us}
        )
        Holding.objects.create(account=acc_dep, security=sec_us, shares=10, current_price=100)

        # Sub-category 2: Intl Equities
        cat_intl, _ = AssetClassCategory.objects.get_or_create(
            code="INTL_EQ",
            defaults={"label": "Intl Equities", "parent": cat_parent_eq, "sort_order": 2},
        )
        cat_intl.parent = cat_parent_eq
        cat_intl.save()

        ac_intl, _ = AssetClass.objects.get_or_create(
            name="Intl Stocks", defaults={"category": cat_intl, "expected_return": 0.1}
        )
        sec_intl, _ = Security.objects.get_or_create(
            ticker="VXUS", defaults={"name": "VXUS", "asset_class": ac_intl}
        )
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
        # The Category Label itself is also hidden in this case because it's only shown in the subtotal row or if explicitly headered (which it isn't).
        # self.assertIn('US Equities', content)
        self.assertNotIn(
            "US Equities Total",
            content,
            "Redundant Category Total for US Equities should be hidden.",
        )

        # Group 'Equities Parent' has 2 Asset Classes (US Stocks + Intl Stocks) -> Group Total SHOWN
        self.assertIn("Equities Parent Total", content, "Group Total for Equities should be shown.")

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
        cat_eq, _ = AssetClassCategory.objects.get_or_create(
            code="EQUITIES", defaults={"label": "Equities", "sort_order": 1}
        )
        ac_us, _ = AssetClass.objects.get_or_create(name="US Stocks", defaults={"category": cat_eq})
        sec_us, _ = Security.objects.get_or_create(
            ticker="VTI", defaults={"name": "VTI", "asset_class": ac_us}
        )

        # Account
        acc_tax = Account.objects.create(
            user=self.user,
            name="My Taxable",
            account_type=AccountType.objects.get(code="TAXABLE"),
            institution=self.institution,
        )

        # Holding: $1000 VTI
        Holding.objects.create(account=acc_tax, security=sec_us, shares=10, current_price=100)

        # Targets: Set US Stocks to 50% for Taxable (implies 50% cash if validated, or just 50 target)
        # We need to create TargetAllocation objects
        TargetAllocation.objects.create(
            user=self.user, account_type=acc_tax.account_type, asset_class=ac_us, target_pct=50
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
        ac_intl, _ = AssetClass.objects.get_or_create(
            name="Intl Stocks", defaults={"category": cat_eq}
        )
        sec_intl, _ = Security.objects.get_or_create(
            ticker="VXUS", defaults={"name": "VXUS", "asset_class": ac_intl}
        )
        Holding.objects.create(account=acc_tax, security=sec_intl, shares=10, current_price=50)
        # Add target for Intl: 40%
        TargetAllocation.objects.create(
            user=self.user, account_type=acc_tax.account_type, asset_class=ac_intl, target_pct=40
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
        self.client.force_login(self.user)

        self.account = Account.objects.create(
            user=self.user,
            name="My Roth",
            account_type=self.type_roth,
            institution=self.institution,
        )

    def test_holdings_view(self) -> None:
        url = reverse("portfolio:holdings")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portfolio/holdings.html")
        self.assertIn("holding_groups", response.context)
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

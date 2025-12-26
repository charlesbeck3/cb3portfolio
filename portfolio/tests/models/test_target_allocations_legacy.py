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
from portfolio.tests.base import PortfolioTestMixin
from portfolio.tests.fixtures.mocks import MockMarketPrices

User = get_user_model()


class TargetAllocationViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
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

        self.category_cash, _ = AssetClassCategory.objects.get_or_create(
            code="CASH", defaults={"label": "Cash", "sort_order": 10}
        )
        self.asset_class_cash, _ = AssetClass.objects.get_or_create(
            name=AssetClass.CASH_NAME, defaults={"category": self.category_cash}
        )
        self.cash, _ = Security.objects.get_or_create(
            ticker="CASH", defaults={"name": "Cash", "asset_class": self.asset_class_cash}
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
            account=self.acc_tax, security=self.cash, shares=2000, current_price=1
        )

        # Setup Strategies
        self.strategy_conservative = AllocationStrategy.objects.create(
            user=self.user, name="Conservative"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_conservative, asset_class=self.ac_us, target_percent=40
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_conservative,
            asset_class=self.asset_class_cash,
            target_percent=60,
        )

        self.strategy_aggressive = AllocationStrategy.objects.create(
            user=self.user, name="Aggressive"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_aggressive, asset_class=self.ac_us, target_percent=90
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_aggressive, asset_class=self.asset_class_cash, target_percent=10
        )

    def test_initial_calculation(self) -> None:
        """Verify context data includes strategies and totals."""
        url = reverse("portfolio:target_allocations")

        with MockMarketPrices({"VTI": Decimal("100.00"), "CASH": Decimal("1.00")}):
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
        self.assertFalse(
            AccountTypeStrategyAssignment.objects.filter(
                user=self.user, account_type=self.type_taxable
            ).exists()
        )

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
            allocation_strategy=self.strategy_aggressive,
        )

        url = reverse("portfolio:target_allocations")

        # Post empty string for Roth
        data = {
            f"strategy_at_{self.type_roth.id}": "",
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        # Verify assignment is gone
        self.assertFalse(
            AccountTypeStrategyAssignment.objects.filter(
                user=self.user, account_type=self.type_roth
            ).exists()
        )

    def test_redundant_subtotals(self) -> None:
        """Verify redundant subtotal rows are suppressed/shown correctly."""
        # Add another category with 1 asset
        bond_cat = AssetClassCategory.objects.create(label="Test Bonds", code="BONDS", sort_order=2)
        AssetClass.objects.create(name="US Bond", category=bond_cat)

        # Ensure Equities has multiple assets (US Stocks + Intl Stocks)
        self.cat_eq.label = "Stocks"
        self.cat_eq.save()
        AssetClass.objects.create(name="Intl Stock", category=self.cat_eq)

        with MockMarketPrices({}):
            response = self.client.get(reverse("portfolio:target_allocations"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # Single asset category -> No subtotal
        self.assertNotIn("Test Bonds Total", content)

        # Multi asset category -> Has subtotal
        self.assertIn("Stocks Total", content)

    def test_all_cash_strategy_allocation(self) -> None:
        """Verify 'All Cash' strategy calculation (repro for cash zero bug)."""
        # Create Deposit Account Type (if not exists)
        type_dep, _ = AssetClassCategory.objects.get_or_create(
            code="CASH_ACCOUNTS", defaults={"label": "Cash & Equivalents", "sort_order": 10}
        )
        # Note: In mixin typ_dep might differ, using explicit creation for safety or relying on mixin if standard.
        # Actually, let's reuse the existing ac_cash / sec_cash setup from setUp,
        # but we need an account with pure CASH strategy.

        # Create "All Cash" Strategy
        strategy_cash = AllocationStrategy.objects.create(user=self.user, name="All Cash")
        # 100% to Cash Asset Class
        TargetAllocation.objects.create(
            strategy=strategy_cash,
            asset_class=self.asset_class_cash,
            target_percent=AllocationStrategy.TOTAL_ALLOCATION_PCT,
        )

        # Create specific cash account
        acc_cash = Account.objects.create(
            user=self.user,
            name="WF Cash",
            portfolio=self.portfolio,
            account_type=self.type_taxable,  # Can use taxable for simplicity, or type_dep if strict
            institution=self.institution,
            allocation_strategy=strategy_cash,  # Assign strategy
        )

        # Add Value to account (via holding)
        Holding.objects.create(
            account=acc_cash, security=self.cash, shares=Decimal("150000"), current_price=1
        )

        # Mock prices (needed for view/service)
        with MockMarketPrices({"VTI": Decimal("100.00"), "CASH": Decimal("1.00")}):
            # We can test via the Service directly (as per repro) OR via the View.
            # Testing via View is more integration-testy.
            # Let's inspect the Context from the view.
            response = self.client.get(reverse("portfolio:target_allocations"))

        self.assertEqual(response.status_code, 200)
        context = response.context

        # Verify Cash Row Calculation
        rows = context["allocation_rows_money"]
        cash_row = next((r for r in rows if r["asset_class_name"] == AssetClass.CASH_NAME), None)
        self.assertIsNotNone(cash_row)
        if cash_row:
            # Find our account in the groups
            # Since account_type is type_taxable (from setup above), look there.
            # Wait, strict repro used type_dep. Let's find where acc_cash ended up.

            target_col = None
            for g in cash_row["account_types"]:
                for acc in g["accounts"]:
                    if acc["id"] == acc_cash.id:
                        target_col = acc
                        break
                if target_col:
                    break

            self.assertIsNotNone(target_col, "Account column not found in Cash row")
            assert target_col is not None

            # Assert Target == Current (150k)
            # target_raw is Decimal
            self.assertEqual(target_col["policy_raw"], Decimal("150000.00"))
            self.assertEqual(target_col["policy_raw"], Decimal("150000.00"))
            self.assertGreater(target_col["actual_raw"], 0)

    def test_fixed_income_subtotal_and_display(self) -> None:
        """Verify subtotal aggregation and percent display format (repro for partial subtotal & dollar sign bug)."""
        # Create FI Category
        cat_fi, _ = AssetClassCategory.objects.get_or_create(
            code="FIXED_INCOME", defaults={"label": "Fixed Income", "sort_order": 5}
        )

        # Create Assets: TIPS and TotalBond
        ac_tips, _ = AssetClass.objects.get_or_create(
            name="Inflation Adjusted Bond", defaults={"category": cat_fi}
        )
        ac_bnd, _ = AssetClass.objects.get_or_create(
            name="Total Bond Market", defaults={"category": cat_fi}
        )

        # Create reusable 'Cash' asset/category if needed (already in setUp? yes ac_cash)
        # Using self.asset_class_cash from setUp

        # Create dedicated Account Type to isolate calculation
        type_fi, _ = AssetClassCategory.objects.get_or_create(
            code="FI_TYPE_GROUP", defaults={"label": "FI Group", "sort_order": 99}
        )
        # Note: AccountType is a model, AssetClassCategory is for assets.
        # Mistake in my previous thought process or just typo in variable name?
        # AccountType model check:
        from portfolio.models import AccountType

        type_fi_obj, _ = AccountType.objects.get_or_create(
            code="FI_TEST_TYPE",
            defaults={
                "label": "FI Test Accounts",
                "group": self.group_deposits,  # Use existing group from mixin
                "tax_treatment": "TAXABLE",
            },
        )

        # Create Account (using dedicated type)
        acc_fi = Account.objects.create(
            user=self.user,
            name="My FI Account",
            portfolio=self.portfolio,
            account_type=type_fi_obj,
            institution=self.institution,
        )

        # Add Cash Holding to give account value
        # 150k value
        Holding.objects.create(
            account=acc_fi, security=self.cash, shares=Decimal("150000"), current_price=1
        )

        # Create Strategy: 50% TIPS, 50% Cash
        strategy_fi = AllocationStrategy.objects.create(user=self.user, name="Half TIPS")
        TargetAllocation.objects.create(
            strategy=strategy_fi, asset_class=ac_tips, target_percent=Decimal("50.00")
        )
        TargetAllocation.objects.create(
            strategy=strategy_fi, asset_class=self.asset_class_cash, target_percent=Decimal("50.00")
        )

        # Assign Strategy
        acc_fi.allocation_strategy = strategy_fi
        acc_fi.save()

        # Mock Prices
        with MockMarketPrices(
            {
                "CASH": Decimal("1.00"),
                "VTI": Decimal("100.00"),
            }
        ):  # VTI needed for other accounts in setUp?
            # Get Context (Percent Mode)
            response = self.client.get(reverse("portfolio:target_allocations") + "?mode=percent")

        self.assertEqual(response.status_code, 200)
        context = response.context
        rows_pct = context["allocation_rows_percent"]

        # 1. Verify Subtotal Calculation (50% of account)
        # Find FI subtotal
        fi_row_pct = next(
            (r for r in rows_pct if "Fixed Income" in r["asset_class_name"] and r["is_subtotal"]),
            None,
        )
        self.assertIsNotNone(fi_row_pct, "Fixed Income Total row not found")

        if fi_row_pct:
            # Find group for our account type (type_fi_obj)
            group_fi = next(
                (g for g in fi_row_pct["account_types"] if g["code"] == "FI_TEST_TYPE"), None
            )
            self.assertIsNotNone(group_fi)
            if group_fi:
                # Should be "50.0" raw (percent value)
                self.assertAlmostEqual(
                    Decimal(str(group_fi["effective_pct"])), Decimal("50.0"), places=1
                )

        # 2. Verify Individual Account Display (No Dollar Signs)
        tips_row = next(
            (r for r in rows_pct if r["asset_class_name"] == "Inflation Adjusted Bond"), None
        )
        self.assertIsNotNone(tips_row)
        if tips_row:
            group_tips = next(
                (g for g in tips_row["account_types"] if g["code"] == "FI_TEST_TYPE"), None
            )
            if group_tips:
                acc_col = next((a for a in group_tips["accounts"] if a["id"] == acc_fi.id), None)
                self.assertIsNotNone(acc_col)
                if acc_col:
                    # Check display string
                    self.assertIn("%", acc_col["policy"])
                    # Check display string
                    self.assertIn("%", acc_col["policy"])
                    self.assertNotIn("$", acc_col["policy"])

    def test_assign_account_strategy_persists_and_renders(self) -> None:
        """Verify individual account strategy assignment persists and renders in select box (repro for display bug)."""
        url = reverse("portfolio:target_allocations")

        # 1. Assign strategy to account via POST
        data = {
            f"strategy_acc_{self.acc_roth.id}": str(self.strategy_conservative.id),
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, url)

        # 2. Verify persistence in DB
        self.acc_roth.refresh_from_db()
        self.assertEqual(self.acc_roth.allocation_strategy, self.strategy_conservative)

        # 3. Verify rendering in GET response
        with MockMarketPrices({"VTI": Decimal("100.00"), "CASH": Decimal("1.00")}):
            response = self.client.get(url)  # Default mode is percent, which has the select box

        content = response.content.decode()

        # The option should be selected
        expected_selected = f'value="{self.strategy_conservative.id}" selected'
        self.assertIn(expected_selected, content)

    def _strip_html(self, value: str) -> str:
        import re

        clean = re.sub("<[^<]+?>", "", value)
        return clean.replace(")", "").replace("(", "-").replace("$", "").replace(",", "").strip()

    def test_category_subtotal_calculation(self) -> None:
        """Verify category and group subtotal calculation logic (repro for subtotal bug)."""
        # Create a nested structure:
        # Group: GLOBAL_EQUITIES
        #   Cat A: US_LARGE
        #   Cat B: INTL_LARGE

        parent_cat = AssetClassCategory.objects.create(
            code="GLOBAL_EQ", label="Global Equities", sort_order=20
        )
        cat_us = AssetClassCategory.objects.create(
            code="US_LARGE", label="US Large Cap", parent=parent_cat, sort_order=1
        )
        cat_intl = AssetClassCategory.objects.create(
            code="INTL_LARGE", label="Intl Large Cap", parent=parent_cat, sort_order=2
        )

        ac_us = AssetClass.objects.create(name="US Large Asset", category=cat_us)
        ac_us_2 = AssetClass.objects.create(
            name="US Large Growth", category=cat_us
        )  # Trigger Subtotal
        ac_intl = AssetClass.objects.create(name="Intl Large Asset", category=cat_intl)

        sec_us = Security.objects.create(ticker="USL", name="US Large ETF", asset_class=ac_us)
        sec_us_2 = Security.objects.create(ticker="USG", name="US Growth ETF", asset_class=ac_us_2)
        sec_intl = Security.objects.create(ticker="INT", name="Intl ETF", asset_class=ac_intl)

        # Add Holdings to Taxable Account (from setUp)
        Holding.objects.create(
            account=self.acc_tax,
            security=sec_us,
            shares=Decimal("10"),
            current_price=Decimal("150.00"),
        )  # $1500
        Holding.objects.create(
            account=self.acc_tax,
            security=sec_us_2,
            shares=Decimal("10"),
            current_price=Decimal("100.00"),
        )  # $1000
        Holding.objects.create(
            account=self.acc_tax,
            security=sec_intl,
            shares=Decimal("10"),
            current_price=Decimal("100.00"),
        )  # $1000

        # Assign Strategy to Account
        strategy_growth = AllocationStrategy.objects.create(user=self.user, name="Global Growth")
        # Target: 60% US (split), 40% Intl
        TargetAllocation.objects.create(
            strategy=strategy_growth, asset_class=ac_us, target_percent=Decimal("30")
        )
        TargetAllocation.objects.create(
            strategy=strategy_growth, asset_class=ac_us_2, target_percent=Decimal("30")
        )
        TargetAllocation.objects.create(
            strategy=strategy_growth, asset_class=ac_intl, target_percent=Decimal("40")
        )

        self.acc_tax.allocation_strategy = strategy_growth
        self.acc_tax.save()

        # Use simple Pricing Mock that returns values such that View uses Current Prices from Holdings if Mock returns nothing?
        # Or better, just mock VTI/CASH and our new tickers.
        with MockMarketPrices({}):
            # Logic in `calculate_allocations` might rely on current_price in Holding if not in map?
            # `Portfolio.to_dataframe` uses `holding.current_price`.
            # We set `current_price` on creation.
            # So we don't strictly need `get_prices` if we trust the DB values.
            # But View might trigger a pricing update? Current `TargetAllocationViewService` does not trigger update.

            response = self.client.get(reverse("portfolio:target_allocations") + "?mode=dollar")

        self.assertEqual(response.status_code, 200)
        rows = response.context["allocation_rows_money"]

        # US Large Cap Subtotal Row (should verify Sum of USL + USG = 1500 + 1000 = 2500)
        # Note: Depending on sort order, implementation might group them.
        # Check for row with label "US Large Cap Total"
        subtotal_row = next(
            (r for r in rows if r["is_subtotal"] and "US Large Cap" in r["asset_class_name"]), None
        )
        self.assertIsNotNone(subtotal_row)
        assert subtotal_row is not None

        # Find column for Taxable
        group = next(
            (g for g in subtotal_row["account_types"] if g["code"] == self.type_taxable.code), None
        )
        self.assertIsNotNone(group)
        assert group is not None
        # "2,500" or "2500"
        self.assertEqual(self._strip_html(group["actual"]), "2500")

        # Group Total Row "Global Equities" (Sum of 2500 + 1000 = 3500)
        group_row = next(
            (r for r in rows if r["is_group_total"] and "Global Equities" in r["asset_class_name"]),
            None,
        )
        self.assertIsNotNone(group_row)
        assert group_row is not None

        group = next(
            (g for g in group_row["account_types"] if g["code"] == self.type_taxable.code), None
        )
        self.assertIsNotNone(group)
        assert group is not None
        self.assertEqual(self._strip_html(group["actual"]), "3500")

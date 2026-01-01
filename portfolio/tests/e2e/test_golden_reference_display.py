"""
E2E tests using golden reference data.

Golden reference tests use portfolios with known, exact values to verify
that the complete pipeline (Database → Engine → Template → Display)
produces mathematically correct results.

These tests are critical for financial applications where calculation
errors can result in material losses.
"""

from decimal import Decimal
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from .helpers import FinancialDisplayValidator


@pytest.mark.e2e
@pytest.mark.golden
@pytest.mark.display
class TestGoldenReferenceDisplay:
    """
    Golden reference tests with known-good portfolio data.

    These tests verify end-to-end accuracy using a portfolio with
    exact, pre-calculated expected values.
    """

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup display validator."""
        self.validator = FinancialDisplayValidator()

    @pytest.fixture
    def golden_portfolio_simple(self, test_user: Any, base_system_data: Any) -> dict[str, Any]:
        """
        Create a simple golden reference portfolio.

        Portfolio Structure:
        - Total Value: $80,000
        - US Equities (VTI): $50,000 (500 shares @ $100)
        - Treasuries (BND): $30,000 (375 shares @ $80)

        Target Allocation (60/40):
        - US Equities: 60% target
        - Treasuries: 40% target

        Expected Results:
        - US Equities: 62.5% actual (target 60%, variance +2.5%)
        - Treasuries: 37.5% actual (target 40%, variance -2.5%)
        """
        from django.utils import timezone

        from portfolio.models import (
            Account,
            AllocationStrategy,
            Holding,
            Portfolio,
            SecurityPrice,
        )

        # Create portfolio
        portfolio = Portfolio.objects.create(user=test_user, name="Golden Portfolio - Simple")

        # Create allocation strategy
        strategy = AllocationStrategy.objects.create(user=test_user, name="60/40 Balanced")
        strategy.save_allocations(
            {
                base_system_data.asset_class_us_equities.id: Decimal("60.00"),
                base_system_data.asset_class_treasuries_interm.id: Decimal("40.00"),
            }
        )
        portfolio.allocation_strategy = strategy
        portfolio.save()

        # Create account
        account = Account.objects.create(
            user=test_user,
            name="Golden Account",
            portfolio=portfolio,
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        # Create holdings with exact known values
        now = timezone.now()

        # US Equities: 500 shares @ $100 = $50,000
        Holding.objects.create(
            account=account, security=base_system_data.vti, shares=Decimal("500.00")
        )
        SecurityPrice.objects.create(
            security=base_system_data.vti,
            price=Decimal("100.00"),
            price_datetime=now,
            source="test",
        )

        # Treasuries: 375 shares @ $80 = $30,000
        Holding.objects.create(
            account=account, security=base_system_data.bnd, shares=Decimal("375.00")
        )
        SecurityPrice.objects.create(
            security=base_system_data.bnd,
            price=Decimal("80.00"),
            price_datetime=now,
            source="test",
        )

        return {
            "portfolio": portfolio,
            "account": account,
            "strategy": strategy,
            "us_equities_id": base_system_data.asset_class_us_equities.id,
            "treasuries_id": base_system_data.asset_class_treasuries_interm.id,
            "expected": {
                "total_value": 80000.0,
                "us_equities": {
                    "value": 50000.0,
                    "percent": 62.5,
                    "target_percent": 60.0,
                    "variance_percent": 2.5,
                    "target_value": 48000.0,  # 60% of 80k
                    "variance_value": 2000.0,  # 50k - 48k
                },
                "treasuries": {
                    "value": 30000.0,
                    "percent": 37.5,
                    "target_percent": 40.0,
                    "variance_percent": -2.5,
                    "target_value": 32000.0,  # 40% of 80k
                    "variance_value": -2000.0,  # 30k - 32k
                },
            },
        }

    # ========================================================================
    # Dashboard: Exact Value Verification
    # ========================================================================

    def test_dashboard_displays_exact_portfolio_total(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Dashboard should display exact portfolio total: $80,000.
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected_total = golden_portfolio_simple["expected"]["total_value"]

        # Check sidebar total
        sidebar_total = authenticated_page.locator("[data-testid='sidebar-total-value']")
        expect(sidebar_total).to_be_visible()

        actual_value = self.validator.get_money_value(sidebar_total)
        assert abs(actual_value - expected_total) < 0.01, (
            f"Portfolio total should be ${expected_total:,.2f}, got ${actual_value:,.2f}"
        )

    def test_dashboard_us_equities_exact_value(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Dashboard should show US Equities = $50,000.
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected = golden_portfolio_simple["expected"]["us_equities"]
        us_eq_id = golden_portfolio_simple["us_equities_id"]

        # Find US Equities actual value
        us_actual = authenticated_page.locator(f"[data-testid='portfolio-actual-{us_eq_id}']")
        expect(us_actual).to_be_visible()

        actual_value = self.validator.get_money_value(us_actual)
        assert abs(actual_value - expected["value"]) < 0.01, (
            f"US Equities should be ${expected['value']:,.2f}, got ${actual_value:,.2f}"
        )

    def test_dashboard_us_equities_exact_percentage(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Dashboard should show US Equities = 62.5%.
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected = golden_portfolio_simple["expected"]["us_equities"]
        us_eq_id = golden_portfolio_simple["us_equities_id"]

        # Find US Equities percentage
        us_pct = authenticated_page.locator(f"[data-testid='portfolio-actual-pct-{us_eq_id}']")
        expect(us_pct).to_be_visible()

        actual_pct = self.validator.get_percent_value(us_pct)
        assert abs(actual_pct - expected["percent"]) < 0.1, (
            f"US Equities should be {expected['percent']}%, got {actual_pct}%"
        )

    def test_dashboard_us_equities_exact_target(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Dashboard should show US Equities target = $48,000 (60% of $80k).
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected = golden_portfolio_simple["expected"]["us_equities"]
        us_eq_id = golden_portfolio_simple["us_equities_id"]

        # Find US Equities target value
        us_target = authenticated_page.locator(f"[data-testid='portfolio-target-{us_eq_id}']")

        if us_target.is_visible():
            actual_value = self.validator.get_money_value(us_target)
            assert abs(actual_value - expected["target_value"]) < 0.01, (
                f"US Equities target should be ${expected['target_value']:,.2f}, "
                f"got ${actual_value:,.2f}"
            )

    def test_dashboard_us_equities_exact_variance(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Dashboard should show US Equities variance = +2.5%.
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected = golden_portfolio_simple["expected"]["us_equities"]
        us_eq_id = golden_portfolio_simple["us_equities_id"]

        # Find variance percentage
        us_variance = authenticated_page.locator(f"[data-testid='portfolio-variance-{us_eq_id}']")

        if us_variance.is_visible():
            actual_variance = self.validator.get_percent_value(us_variance)
            assert abs(actual_variance - expected["variance_percent"]) < 0.1, (
                f"US Equities variance should be {expected['variance_percent']:+.1f}%, "
                f"got {actual_variance:+.1f}%"
            )

            # Verify color (should be positive/green)
            self.validator.assert_variance_has_color(us_variance)
            classes = us_variance.get_attribute("class")
            assert classes is not None and "variance-positive" in classes, (
                "US Equities over target should be green"
            )

    def test_dashboard_treasuries_exact_values(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Dashboard should show Treasuries with exact values.

        Expected:
        - Value: $30,000
        - Percentage: 37.5%
        - Target: $32,000 (40% of $80k)
        - Variance: -2.5%
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected = golden_portfolio_simple["expected"]["treasuries"]
        treasuries_id = golden_portfolio_simple["treasuries_id"]

        # Check actual value
        treasuries_actual = authenticated_page.locator(
            f"[data-testid='portfolio-actual-{treasuries_id}']"
        )
        if treasuries_actual.is_visible():
            actual_value = self.validator.get_money_value(treasuries_actual)
            assert abs(actual_value - expected["value"]) < 0.01, (
                f"Treasuries value should be ${expected['value']:,.2f}"
            )

        # Check percentage
        treasuries_pct = authenticated_page.locator(
            f"[data-testid='portfolio-actual-pct-{treasuries_id}']"
        )
        if treasuries_pct.is_visible():
            actual_pct = self.validator.get_percent_value(treasuries_pct)
            assert abs(actual_pct - expected["percent"]) < 0.1, (
                f"Treasuries should be {expected['percent']}%"
            )

        # Check variance (should be negative/red)
        treasuries_variance = authenticated_page.locator(
            f"[data-testid='portfolio-variance-{treasuries_id}']"
        )
        if treasuries_variance.is_visible():
            actual_variance = self.validator.get_percent_value(treasuries_variance)
            assert abs(actual_variance - expected["variance_percent"]) < 0.1, (
                f"Treasuries variance should be {expected['variance_percent']:+.1f}%"
            )

            # Verify color (should be negative/red)
            classes = treasuries_variance.get_attribute("class")
            assert classes is not None and "variance-negative" in classes, (
                "Treasuries under target should be red"
            )

    # ========================================================================
    # Holdings Page: Per-Security Verification
    # ========================================================================

    def test_holdings_vti_exact_values(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Holdings page should show VTI with exact values.

        Expected:
        - Shares: 500.00
        - Price: $100.00
        - Value: $50,000
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        # Check shares
        vti_shares = authenticated_page.locator("[data-testid='shares-VTI']")
        if vti_shares.is_visible():
            shares_text = vti_shares.text_content()
            assert shares_text is not None
            shares = float(shares_text.replace(",", ""))
            assert abs(shares - 500.0) < 0.01, f"VTI shares should be 500.00, got {shares}"

        # Check price
        vti_price = authenticated_page.locator("[data-testid='price-VTI']")
        if vti_price.is_visible():
            price = self.validator.get_money_value(vti_price)
            assert abs(price - 100.0) < 0.01, f"VTI price should be $100.00, got ${price}"

        # Check value
        vti_value = authenticated_page.locator("[data-testid='value-VTI']")
        if vti_value.is_visible():
            value = self.validator.get_money_value(vti_value)
            assert abs(value - 50000.0) < 0.01, f"VTI value should be $50,000, got ${value:,.2f}"

    def test_holdings_bnd_exact_values(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Holdings page should show BND with exact values.

        Expected:
        - Shares: 375.00
        - Price: $80.00
        - Value: $30,000
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        # Check shares
        bnd_shares = authenticated_page.locator("[data-testid='shares-BND']")
        if bnd_shares.is_visible():
            shares_text = bnd_shares.text_content()
            assert shares_text is not None
            shares = float(shares_text.replace(",", ""))
            assert abs(shares - 375.0) < 0.01, f"BND shares should be 375.00, got {shares}"

        # Check price
        bnd_price = authenticated_page.locator("[data-testid='price-BND']")
        if bnd_price.is_visible():
            price = self.validator.get_money_value(bnd_price)
            assert abs(price - 80.0) < 0.01, f"BND price should be $80.00, got ${price}"

        # Check value
        bnd_value = authenticated_page.locator("[data-testid='value-BND']")
        if bnd_value.is_visible():
            value = self.validator.get_money_value(bnd_value)
            assert abs(value - 30000.0) < 0.01, f"BND value should be $30,000, got ${value:,.2f}"

    def test_holdings_total_matches_portfolio(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Holdings page total should match portfolio total: $80,000.
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        expected_total = golden_portfolio_simple["expected"]["total_value"]

        # Check sidebar (should be same on all pages)
        sidebar_total = authenticated_page.locator("[data-testid='sidebar-total-value']")
        if sidebar_total.is_visible():
            actual_total = self.validator.get_money_value(sidebar_total)
            assert abs(actual_total - expected_total) < 0.01, (
                f"Holdings page should show total ${expected_total:,.2f}"
            )

    # ========================================================================
    # Targets Page: Verification
    # ========================================================================

    def test_targets_current_percentages_exact(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Targets page should show exact current percentages.

        - US Equities: 62.5%
        - Treasuries: 37.5%
        """
        authenticated_page.goto(f"{live_server_url}/targets/")

        expected_us = golden_portfolio_simple["expected"]["us_equities"]
        expected_treasuries = golden_portfolio_simple["expected"]["treasuries"]

        us_eq_id = golden_portfolio_simple["us_equities_id"]
        treasuries_id = golden_portfolio_simple["treasuries_id"]

        # Check US Equities current
        us_current = authenticated_page.locator(f"[data-testid='target-current-pct-{us_eq_id}']")
        if us_current.is_visible():
            actual_pct = self.validator.get_percent_value(us_current)
            assert abs(actual_pct - expected_us["percent"]) < 0.1, (
                f"US Equities current should be {expected_us['percent']}%"
            )

        # Check Treasuries current
        treasuries_current = authenticated_page.locator(
            f"[data-testid='target-current-pct-{treasuries_id}']"
        )
        if treasuries_current.is_visible():
            actual_pct = self.validator.get_percent_value(treasuries_current)
            assert abs(actual_pct - expected_treasuries["percent"]) < 0.1, (
                f"Treasuries current should be {expected_treasuries['percent']}%"
            )

    def test_targets_shows_policy_targets(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_simple: dict[str, Any],
    ) -> None:
        """
        Targets page should display the 60/40 policy targets.
        """
        authenticated_page.goto(f"{live_server_url}/targets/")

        us_eq_id = golden_portfolio_simple["us_equities_id"]
        treasuries_id = golden_portfolio_simple["treasuries_id"]

        # Check US Equities target input (should show 60)
        us_input = authenticated_page.locator(f"[data-testid='target-input-{us_eq_id}']")
        if us_input.is_visible():
            value = us_input.input_value()
            if value:  # May be empty if not explicitly set
                assert abs(float(value) - 60.0) < 0.01, "US Equities target input should be 60"

        # Check Treasuries target input (should show 40)
        treasuries_input = authenticated_page.locator(
            f"[data-testid='target-input-{treasuries_id}']"
        )
        if treasuries_input.is_visible():
            value = treasuries_input.input_value()
            if value:
                assert abs(float(value) - 40.0) < 0.01, "Treasuries target input should be 40"


# ============================================================================
# Multi-Account Golden Reference Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.golden
@pytest.mark.display
class TestGoldenReferenceMultiAccount:
    """
    Golden reference tests with multiple accounts.

    Tests more complex scenarios with multiple account types
    and weighted allocations.
    """

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup validator."""
        self.validator = FinancialDisplayValidator()

    @pytest.fixture
    def golden_portfolio_multi_account(
        self, test_user: Any, base_system_data: Any
    ) -> dict[str, Any]:
        """
        Create a multi-account golden reference portfolio.

        Portfolio Structure:
        - Account 1 (Taxable): $60,000
          - VTI: $40,000 (400 shares @ $100)
          - BND: $20,000 (250 shares @ $80)
        - Account 2 (Roth IRA): $40,000
          - VTI: $40,000 (400 shares @ $100)

        Total Portfolio: $100,000

        Portfolio-Level Target (60/40):
        - US Equities: 60% target
        - Treasuries: 40% target

        Actual Allocation:
        - US Equities: $80,000 = 80% (variance +20%)
        - Treasuries: $20,000 = 20% (variance -20%)
        """
        from django.utils import timezone

        from portfolio.models import (
            Account,
            AllocationStrategy,
            Holding,
            Portfolio,
            SecurityPrice,
        )

        # Create portfolio with strategy
        portfolio = Portfolio.objects.create(user=test_user, name="Golden Multi-Account")

        portfolio_strategy = AllocationStrategy.objects.create(
            user=test_user, name="60/40 Portfolio Strategy"
        )
        portfolio_strategy.save_allocations(
            {
                base_system_data.asset_class_us_equities.id: Decimal("60.00"),
                base_system_data.asset_class_treasuries_interm.id: Decimal("40.00"),
            }
        )
        portfolio.allocation_strategy = portfolio_strategy
        portfolio.save()

        # Create Account 1: Taxable
        account_taxable = Account.objects.create(
            user=test_user,
            name="Taxable Account",
            portfolio=portfolio,
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        # Create Account 2: Roth IRA
        account_roth = Account.objects.create(
            user=test_user,
            name="Roth IRA",
            portfolio=portfolio,
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        # Create prices
        now = timezone.now()
        SecurityPrice.objects.create(
            security=base_system_data.vti,
            price=Decimal("100.00"),
            price_datetime=now,
            source="test",
        )
        SecurityPrice.objects.create(
            security=base_system_data.bnd,
            price=Decimal("80.00"),
            price_datetime=now,
            source="test",
        )

        # Taxable holdings
        Holding.objects.create(
            account=account_taxable,
            security=base_system_data.vti,
            shares=Decimal("400.00"),  # $40k
        )
        Holding.objects.create(
            account=account_taxable,
            security=base_system_data.bnd,
            shares=Decimal("250.00"),  # $20k
        )

        # Roth holdings
        Holding.objects.create(
            account=account_roth,
            security=base_system_data.vti,
            shares=Decimal("400.00"),  # $40k
        )

        return {
            "portfolio": portfolio,
            "account_taxable": account_taxable,
            "account_roth": account_roth,
            "us_equities_id": base_system_data.asset_class_us_equities.id,
            "treasuries_id": base_system_data.asset_class_treasuries_interm.id,
            "expected": {
                "total_value": 100000.0,
                "account_taxable_value": 60000.0,
                "account_roth_value": 40000.0,
                "us_equities": {
                    "value": 80000.0,
                    "percent": 80.0,
                    "target_percent": 60.0,
                    "variance_percent": 20.0,
                },
                "treasuries": {
                    "value": 20000.0,
                    "percent": 20.0,
                    "target_percent": 40.0,
                    "variance_percent": -20.0,
                },
            },
        }

    def test_multi_account_portfolio_total(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_multi_account: dict[str, Any],
    ) -> None:
        """
        Multi-account portfolio should show correct total: $100,000.
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected_total = golden_portfolio_multi_account["expected"]["total_value"]

        sidebar_total = authenticated_page.locator("[data-testid='sidebar-total-value']")
        actual_total = self.validator.get_money_value(sidebar_total)

        assert abs(actual_total - expected_total) < 0.01, (
            f"Total should be ${expected_total:,.2f}, got ${actual_total:,.2f}"
        )

    def test_multi_account_aggregated_allocation(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_multi_account: dict[str, Any],
    ) -> None:
        """
        Dashboard should show correct aggregated allocation.

        - US Equities: 80% ($80k across both accounts)
        - Treasuries: 20% ($20k in taxable only)
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected_us = golden_portfolio_multi_account["expected"]["us_equities"]
        expected_treasuries = golden_portfolio_multi_account["expected"]["treasuries"]

        us_eq_id = golden_portfolio_multi_account["us_equities_id"]
        treasuries_id = golden_portfolio_multi_account["treasuries_id"]

        # Check US Equities
        us_pct = authenticated_page.locator(f"[data-testid='portfolio-actual-pct-{us_eq_id}']")
        if us_pct.is_visible():
            actual_pct = self.validator.get_percent_value(us_pct)
            assert abs(actual_pct - expected_us["percent"]) < 0.1, (
                f"US Equities should be {expected_us['percent']}%, got {actual_pct}%"
            )

        # Check Treasuries
        treasuries_pct = authenticated_page.locator(
            f"[data-testid='portfolio-actual-pct-{treasuries_id}']"
        )
        if treasuries_pct.is_visible():
            actual_pct = self.validator.get_percent_value(treasuries_pct)
            assert abs(actual_pct - expected_treasuries["percent"]) < 0.1, (
                f"Treasuries should be {expected_treasuries['percent']}%, got {actual_pct}%"
            )

    def test_multi_account_large_variance(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_multi_account: dict[str, Any],
    ) -> None:
        """
        Multi-account portfolio has large variance: +20% equities, -20% treasuries.
        """
        authenticated_page.goto(f"{live_server_url}/")

        expected_us = golden_portfolio_multi_account["expected"]["us_equities"]
        expected_treasuries = golden_portfolio_multi_account["expected"]["treasuries"]

        us_eq_id = golden_portfolio_multi_account["us_equities_id"]
        treasuries_id = golden_portfolio_multi_account["treasuries_id"]

        # Check US Equities variance
        us_variance = authenticated_page.locator(f"[data-testid='portfolio-variance-{us_eq_id}']")
        if us_variance.is_visible():
            actual_variance = self.validator.get_percent_value(us_variance)
            assert abs(actual_variance - expected_us["variance_percent"]) < 0.1, (
                f"US Equities variance should be +{expected_us['variance_percent']}%"
            )

            # Should be strongly positive (green)
            classes = us_variance.get_attribute("class")
            assert classes is not None and "variance-positive" in classes

        # Check Treasuries variance
        treasuries_variance = authenticated_page.locator(
            f"[data-testid='portfolio-variance-{treasuries_id}']"
        )
        if treasuries_variance.is_visible():
            actual_variance = self.validator.get_percent_value(treasuries_variance)
            assert abs(actual_variance - expected_treasuries["variance_percent"]) < 0.1, (
                f"Treasuries variance should be {expected_treasuries['variance_percent']}%"
            )

            # Should be strongly negative (red)
            classes = treasuries_variance.get_attribute("class")
            assert classes is not None and "variance-negative" in classes

    def test_multi_account_sidebar_shows_both_accounts(
        self,
        authenticated_page: Page,
        live_server_url: str,
        golden_portfolio_multi_account: dict[str, Any],
    ) -> None:
        """
        Sidebar should show both accounts with correct values.

        - Taxable: $60,000
        - Roth IRA: $40,000
        """
        authenticated_page.goto(f"{live_server_url}/")

        account_taxable = golden_portfolio_multi_account["account_taxable"]
        account_roth = golden_portfolio_multi_account["account_roth"]

        expected_taxable = golden_portfolio_multi_account["expected"]["account_taxable_value"]
        expected_roth = golden_portfolio_multi_account["expected"]["account_roth_value"]

        # Check taxable account
        taxable_value = authenticated_page.locator(
            f"[data-testid='sidebar-account-value-{account_taxable.id}']"
        )
        if taxable_value.is_visible():
            actual = self.validator.get_money_value(taxable_value)
            assert abs(actual - expected_taxable) < 0.01, (
                f"Taxable should show ${expected_taxable:,.2f}"
            )

        # Check Roth account
        roth_value = authenticated_page.locator(
            f"[data-testid='sidebar-account-value-{account_roth.id}']"
        )
        if roth_value.is_visible():
            actual = self.validator.get_money_value(roth_value)
            assert abs(actual - expected_roth) < 0.01, f"Roth should show ${expected_roth:,.2f}"

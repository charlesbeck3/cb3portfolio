"""
E2E tests for edge cases that commonly cause display bugs.

These tests verify the app handles unusual scenarios gracefully:
- Empty portfolios
- Zero values
- Missing prices
- Very large/small numbers
"""

from decimal import Decimal
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from .helpers import FinancialDisplayValidator, create_test_portfolio_with_values


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.display
@pytest.mark.edge_case
class TestDisplayEdgeCases:
    """Edge case tests for display validation."""

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup validator."""
        self.validator = FinancialDisplayValidator()

    # ========================================================================
    # Empty/Zero States
    # ========================================================================

    def test_empty_portfolio_displays_gracefully(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Portfolio with no holdings should display without errors.

        This catches division by zero when calculating percentages.
        """
        from portfolio.models import Portfolio

        Portfolio.objects.create(user=test_user, name="Empty")

        authenticated_page.goto(f"{live_server_url}/")

        # Should not crash or show NaN
        self.validator.assert_no_invalid_values(authenticated_page)

    def test_zero_value_holdings(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Holdings with zero shares should display without NaN.
        """
        from django.utils import timezone

        from portfolio.models import Account, Holding, Portfolio, SecurityPrice

        portfolio = Portfolio.objects.create(user=test_user, name="Test")
        account = Account.objects.create(
            user=test_user,
            name="Test",
            portfolio=portfolio,
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        # Create holding with zero shares
        Holding.objects.create(
            account=account, security=base_system_data.vti, shares=Decimal("0.00")
        )

        SecurityPrice.objects.create(
            security=base_system_data.vti,
            price=Decimal("100.00"),
            price_datetime=timezone.now(),
            source="test",
        )

        authenticated_page.goto(f"{live_server_url}/")

        self.validator.assert_no_invalid_values(authenticated_page)

    # ========================================================================
    # Missing Data
    # ========================================================================

    def test_missing_security_prices_handled(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Holdings without prices should not show NaN.

        This catches errors when price lookups fail.
        """
        from portfolio.models import Account, Holding, Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Test")
        account = Account.objects.create(
            user=test_user,
            name="Test",
            portfolio=portfolio,
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        # Create holding WITHOUT price
        Holding.objects.create(
            account=account, security=base_system_data.vti, shares=Decimal("100.00")
        )
        # Don't create SecurityPrice

        authenticated_page.goto(f"{live_server_url}/")

        # Should not show NaN
        self.validator.assert_no_invalid_values(authenticated_page)

    # ========================================================================
    # Extreme Values
    # ========================================================================

    def test_very_large_numbers_display_correctly(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Very large portfolio values ($10M+) should format correctly.
        """
        # $10 million portfolio
        create_test_portfolio_with_values(
            test_user, base_system_data, us_equities_value=10_000_000.0
        )

        authenticated_page.goto(f"{live_server_url}/")

        self.validator.assert_no_invalid_values(authenticated_page)

        # Should format with commas
        page_content = authenticated_page.content()
        assert "10,000,000" in page_content, "Large numbers should be formatted with commas"

    def test_small_portfolio_displays(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Small portfolio values should display correctly.
        """
        # $100 portfolio
        create_test_portfolio_with_values(test_user, base_system_data, us_equities_value=100.0)

        authenticated_page.goto(f"{live_server_url}/")

        self.validator.assert_no_invalid_values(authenticated_page)

        # Sidebar should show value
        sidebar_total = authenticated_page.locator("[data-testid='sidebar-total-value']")
        expect(sidebar_total).to_be_visible()

    # ========================================================================
    # Multiple Account Types
    # ========================================================================

    def test_multiple_account_types_display(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Multiple account types should all display correctly.
        """
        from django.utils import timezone

        from portfolio.models import Account, Holding, Portfolio, SecurityPrice

        portfolio = Portfolio.objects.create(user=test_user, name="Multi Account")

        # Create Roth account
        roth = Account.objects.create(
            user=test_user,
            name="Roth IRA",
            portfolio=portfolio,
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )
        Holding.objects.create(account=roth, security=base_system_data.vti, shares=Decimal("100"))

        # Create Taxable account
        taxable = Account.objects.create(
            user=test_user,
            name="Taxable",
            portfolio=portfolio,
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )
        Holding.objects.create(account=taxable, security=base_system_data.bnd, shares=Decimal("50"))

        # Create prices
        now = timezone.now()
        SecurityPrice.objects.update_or_create(
            security=base_system_data.vti,
            defaults={"price": Decimal("100"), "price_datetime": now, "source": "test"},
        )
        SecurityPrice.objects.update_or_create(
            security=base_system_data.bnd,
            defaults={"price": Decimal("100"), "price_datetime": now, "source": "test"},
        )

        authenticated_page.goto(f"{live_server_url}/")

        self.validator.assert_no_invalid_values(authenticated_page)

        # Both accounts should appear in sidebar
        page_content = authenticated_page.content()
        assert "Roth IRA" in page_content, "Roth account should appear"
        assert "Taxable" in page_content, "Taxable account should appear"


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.display
@pytest.mark.edge_case
class TestHoldingsEdgeCases:
    """Edge case tests specific to holdings page."""

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup validator."""
        self.validator = FinancialDisplayValidator()

    def test_holdings_page_empty_portfolio(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Holdings page with no holdings should display gracefully.
        """
        from portfolio.models import Portfolio

        Portfolio.objects.create(user=test_user, name="Empty")

        authenticated_page.goto(f"{live_server_url}/holdings/")

        self.validator.assert_no_invalid_values(authenticated_page)

        # Should show empty message or table
        page_content = authenticated_page.content().lower()
        assert "no holdings" in page_content or "holdings-table" in page_content, (
            "Should show empty state or table"
        )

    def test_holdings_with_fractional_shares(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """
        Holdings with fractional shares should display correctly.
        """
        from django.utils import timezone

        from portfolio.models import Account, Holding, Portfolio, SecurityPrice

        portfolio = Portfolio.objects.create(user=test_user, name="Fractional")
        account = Account.objects.create(
            user=test_user,
            name="Test",
            portfolio=portfolio,
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        # Create holding with fractional shares
        Holding.objects.create(
            account=account, security=base_system_data.vti, shares=Decimal("123.4567")
        )

        SecurityPrice.objects.create(
            security=base_system_data.vti,
            price=Decimal("100.00"),
            price_datetime=timezone.now(),
            source="test",
        )

        authenticated_page.goto(f"{live_server_url}/holdings/")

        self.validator.assert_no_invalid_values(authenticated_page)

        # Shares should display
        shares_cell = authenticated_page.locator("[data-testid='shares-VTI']")
        if shares_cell.is_visible():
            text = shares_cell.text_content()
            assert text is not None
            assert "NaN" not in text

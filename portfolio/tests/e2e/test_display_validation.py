"""
Critical display validation tests that apply across all pages.

These tests verify fundamental display requirements:
- No NaN/undefined values on any page
- Consistent formatting across pages
- No JavaScript errors breaking display

Run these tests on EVERY commit.
"""

from typing import Any

import pytest
from playwright.sync_api import Page, expect

from .helpers import FinancialDisplayValidator, create_test_portfolio_with_values


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.display
class TestCriticalDisplayValidation:
    """
    Critical display tests that must pass for ALL pages.

    These are the "smoke tests" for display validation.
    """

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup validator for all tests."""
        self.validator = FinancialDisplayValidator()

    @pytest.fixture
    def test_portfolio(self, test_user: Any, base_system_data: Any) -> dict[str, Any]:
        """Standard test portfolio for all pages."""
        return create_test_portfolio_with_values(
            test_user, base_system_data, us_equities_value=50000.0, bonds_value=30000.0
        )

    # ========================================================================
    # CRITICAL: All Pages Must Have No Invalid Values
    # ========================================================================

    @pytest.mark.parametrize(
        "page_url,page_name",
        [
            ("/", "Dashboard"),
            ("/targets/", "Targets"),
            ("/holdings/", "Holdings"),
        ],
    )
    def test_no_nan_on_any_page(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_portfolio: dict[str, Any],
        page_url: str,
        page_name: str,
    ) -> None:
        """
        CRITICAL: No page should ever display NaN values.

        This is the most important test - it catches the bugs
        you've been experiencing.
        """
        authenticated_page.goto(f"{live_server_url}{page_url}")

        # Assert no NaN anywhere on page
        self.validator.assert_no_invalid_values(authenticated_page)

    @pytest.mark.parametrize(
        "page_url",
        [
            "/",
            "/targets/",
            "/holdings/",
        ],
    )
    def test_no_javascript_errors(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_portfolio: dict[str, Any],
        page_url: str,
    ) -> None:
        """
        Pages should load without JavaScript errors.

        JavaScript errors can cause display to break.
        """
        # Track console errors
        errors: list[str] = []
        authenticated_page.on(
            "console", lambda msg: errors.append(msg.text) if msg.type == "error" else None
        )

        authenticated_page.goto(f"{live_server_url}{page_url}")

        # Allow page to fully load
        authenticated_page.wait_for_load_state("networkidle")

        # Filter out known/acceptable errors
        actual_errors = [
            e
            for e in errors
            if "favicon" not in e.lower()  # Ignore favicon errors
            and "extension" not in e.lower()  # Ignore browser extension errors
        ]

        assert len(actual_errors) == 0, f"JavaScript errors on {page_url}: {actual_errors}"

    # ========================================================================
    # Values Consistent Across Pages
    # ========================================================================

    def test_portfolio_total_consistent_across_pages(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_portfolio: dict[str, Any],
    ) -> None:
        """
        Same portfolio total should appear on all pages.

        Dashboard, holdings, and sidebar should all agree.
        """
        expected_total = test_portfolio["total_value"]

        # Get value from dashboard sidebar
        authenticated_page.goto(f"{live_server_url}/")
        sidebar_total = authenticated_page.locator("[data-testid='sidebar-total-value']")
        dashboard_value = self.validator.get_money_value(sidebar_total)

        # Should match expected (within $1 for rounding)
        assert abs(dashboard_value - expected_total) < 1.0, (
            f"Dashboard shows {dashboard_value}, expected {expected_total}"
        )

        # Check holdings page sidebar (should be same)
        authenticated_page.goto(f"{live_server_url}/holdings/")
        sidebar_total = authenticated_page.locator("[data-testid='sidebar-total-value']")
        holdings_value = self.validator.get_money_value(sidebar_total)

        assert abs(holdings_value - expected_total) < 1.0, (
            f"Holdings shows {holdings_value}, expected {expected_total}"
        )

    # ========================================================================
    # Formatting Standards Applied Everywhere
    # ========================================================================

    @pytest.mark.parametrize("page_url", ["/", "/holdings/"])
    def test_sidebar_has_dollar_signs(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_portfolio: dict[str, Any],
        page_url: str,
    ) -> None:
        """
        Sidebar money values should have $ on every page.
        """
        authenticated_page.goto(f"{live_server_url}{page_url}")

        # Check sidebar total
        sidebar_total = authenticated_page.locator("[data-testid='sidebar-total-value']")
        if sidebar_total.is_visible():
            text = sidebar_total.text_content()
            assert text is not None
            assert "$" in text, f"Sidebar total missing $: {text}"


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.display
class TestPageSpecificValidation:
    """
    Page-specific validation tests.

    These tests verify requirements specific to individual pages.
    """

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup validator."""
        self.validator = FinancialDisplayValidator()

    @pytest.fixture
    def test_portfolio(self, test_user: Any, base_system_data: Any) -> dict[str, Any]:
        """Standard test portfolio."""
        return create_test_portfolio_with_values(
            test_user, base_system_data, us_equities_value=50000.0, bonds_value=30000.0
        )

    def test_dashboard_allocation_tables_visible(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_portfolio: dict[str, Any],
    ) -> None:
        """Dashboard should show allocation tables."""
        authenticated_page.goto(f"{live_server_url}/")

        # Dollar table
        dollar_table = authenticated_page.locator("[data-testid='allocation-table-dollar']")
        expect(dollar_table).to_be_visible()

        # Percent table
        percent_table = authenticated_page.locator("[data-testid='allocation-table-percent']")
        expect(percent_table).to_be_visible()

    def test_holdings_table_visible(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_portfolio: dict[str, Any],
    ) -> None:
        """Holdings page should show holdings table."""
        authenticated_page.goto(f"{live_server_url}/holdings/")

        table = authenticated_page.locator("[data-testid='holdings-table']")
        expect(table).to_be_visible()

    def test_targets_table_visible(
        self,
        authenticated_page: Page,
        live_server_url: str,
        test_portfolio: dict[str, Any],
    ) -> None:
        """Targets page should show allocation tables."""
        authenticated_page.goto(f"{live_server_url}/targets/")

        # At least one allocation table should be visible
        table = authenticated_page.locator("[data-testid^='allocation-table']")
        expect(table.first).to_be_visible()

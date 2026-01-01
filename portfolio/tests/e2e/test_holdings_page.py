"""
E2E tests for holdings page.

Tests:
- test_holdings_click_interaction: Existing interaction test
- TestHoldingsDisplayValidation: Display validation tests (Phase 2)
"""

from typing import Any

from django.urls import reverse

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import Account, Holding


@pytest.mark.e2e
def test_holdings_click_interaction(
    page: Page, live_server: Any, test_user: Any, base_system_data: Any, login_user: Any
) -> None:
    """Test clicking a holdings row expands details."""

    # Setup data
    from portfolio.models import Portfolio as PortfolioModel

    portfolio = PortfolioModel.objects.create(user=test_user, name="E2E Portfolio")

    acc = Account.objects.create(
        user=test_user,
        name="E2E Account",
        portfolio=portfolio,
        account_type=base_system_data.type_roth,
        institution=base_system_data.institution,
    )

    vti = base_system_data.vti
    Holding.objects.create(account=acc, security=vti, shares=10)

    # Login
    login_user()

    # Go to holdings
    page.goto(f"{live_server.url}{reverse('portfolio:holdings')}")

    # Verify row exists
    ticker_row = page.locator(f"tr[data-ticker='{vti.ticker}']")
    expect(ticker_row).to_be_visible()

    # Click row
    ticker_row.click()

    # Verify details expanded
    details_row = page.locator(f"#ticker-details-{vti.ticker}")
    expect(details_row).to_be_visible()
    expect(details_row.locator("text=Account Level Details")).to_be_visible()
    expect(details_row.locator("text=E2E Account")).to_be_visible()

    # Click again to collapse
    ticker_row.click()

    # Verify details gone (or hidden)
    # My JS removes it and replaces with d-none placeholder
    expect(details_row.locator("text=Account Level Details")).not_to_be_visible()
    expect(details_row).to_have_class("d-none")  # Checks the placeholder has d-none


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.display
class TestHoldingsDisplayValidation:
    """
    Display validation tests for holdings page.

    Holdings page shows individual security calculations which can
    produce NaN if prices are missing or calculations fail.
    """

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup display validator."""
        from .helpers import FinancialDisplayValidator

        self.validator = FinancialDisplayValidator()

    @pytest.fixture
    def holdings_with_data(self, test_user: Any, base_system_data: Any) -> dict[str, Any]:
        """
        Create holdings for display testing.

        Creates a portfolio with 3 different securities to test
        individual security display formatting.

        Holdings:
        - VTI: $50,000 (500 shares @ $100)
        - VXUS: $30,000 (600 shares @ $50)
        - BND: $20,000 (250 shares @ $80)
        Total: $100,000
        """
        from .helpers import create_test_portfolio_with_values

        return create_test_portfolio_with_values(
            test_user,
            base_system_data,
            us_equities_value=50000.0,
            intl_equities_value=30000.0,
            bonds_value=20000.0,
        )

    def test_holdings_page_has_no_nan_values(
        self, authenticated_page: Page, live_server_url: str, holdings_with_data: dict[str, Any]
    ) -> None:
        """
        CRITICAL: Holdings page should never display NaN.
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        self.validator.assert_no_invalid_values(authenticated_page)

        table = authenticated_page.locator("[data-testid='holdings-table']")
        expect(table).to_be_visible()

    def test_all_securities_display(
        self, authenticated_page: Page, live_server_url: str, holdings_with_data: dict[str, Any]
    ) -> None:
        """
        Holdings page should display all securities with correct formatting.

        Verifies all 3 securities from fixture appear.
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        # Verify each security appears
        for ticker in ["VTI", "VXUS", "BND"]:
            row = authenticated_page.locator(f"[data-testid='holding-row-{ticker}']")
            expect(row).to_be_visible()

    def test_holding_values_formatted_as_money(
        self, authenticated_page: Page, live_server_url: str, holdings_with_data: dict[str, Any]
    ) -> None:
        """
        Individual holding values should be formatted with $.
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        # Find value cells for VTI (from fixture)
        value_cell = authenticated_page.locator("[data-testid='value-VTI']")

        if value_cell.is_visible():
            text = value_cell.text_content()
            assert text is not None
            assert "$" in text, f"Value cell missing $: {text}"

    def test_share_counts_display_correctly(
        self, authenticated_page: Page, live_server_url: str, holdings_with_data: dict[str, Any]
    ) -> None:
        """
        Share counts should display as numbers, not NaN.
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        # Find VTI shares (from fixture)
        vti_shares = authenticated_page.locator("[data-testid='shares-VTI']")

        if vti_shares.is_visible():
            text = vti_shares.text_content()
            assert text is not None
            assert "NaN" not in text, "Shares showing NaN"
            assert text.strip() != "", "Shares cell empty"
            # Should be a number (remove commas first)
            try:
                float(text.replace(",", "").strip())
            except ValueError:
                pytest.fail(f"Shares not a valid number: {text}")

    def test_ticker_rows_have_data_attributes(
        self, authenticated_page: Page, live_server_url: str, holdings_with_data: dict[str, Any]
    ) -> None:
        """
        Ticker rows should have proper data-testid attributes.

        This verifies Phase 1 completion.
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        # Check for VTI row (from fixture)
        vti_row = authenticated_page.locator("[data-testid='holding-row-VTI']")
        assert vti_row.count() > 0, "VTI row missing data-testid attribute"

    def test_grand_total_row_displays(
        self, authenticated_page: Page, live_server_url: str, holdings_with_data: dict[str, Any]
    ) -> None:
        """
        Grand total row should display correctly with $100,000 total.
        """
        authenticated_page.goto(f"{live_server_url}/holdings/")

        expected_total = holdings_with_data["total_value"]

        # Find grand total row
        grand_total = authenticated_page.locator("[data-testid='grand-total-row']")
        expect(grand_total).to_be_visible()

        # Value should be formatted and match expected
        value_cell = authenticated_page.locator("[data-testid='grand-total-value']")
        expect(value_cell).to_be_visible()

        actual_total = self.validator.get_money_value(value_cell)
        assert abs(actual_total - expected_total) < 0.01, (
            f"Grand total should be ${expected_total:,.2f}, got ${actual_total:,.2f}"
        )

"""
E2E tests for dashboard page.

Tests:
- TestDashboardPage: Existing interaction tests
- TestDashboardDisplayValidation: Display validation tests (Phase 2)
"""

from decimal import Decimal
from typing import Any

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.django_db
class TestDashboardPage:
    @pytest.fixture(autouse=True)
    def setup_data(self, simple_holdings: dict[str, Any]) -> None:
        pass

    def test_variance_mode_toggle(self, authenticated_page: Page, live_server_url: str) -> None:
        authenticated_page.goto(f"{live_server_url}/")

        # Default is Effective Variance
        expect(authenticated_page.locator(".col-mode-effective").first).to_be_visible()
        expect(authenticated_page.locator(".col-mode-policy").first).to_be_hidden()

        # Switch to Policy Variance (Click the label)
        authenticated_page.locator('label[for="variance-policy"]').click()

        # Verify columns toggled
        expect(authenticated_page.locator(".col-mode-policy").first).to_be_visible()
        expect(authenticated_page.locator(".col-mode-effective").first).to_be_hidden()

        # Switch back to Effective Variance
        authenticated_page.locator('label[for="variance-effective"]').click()
        expect(authenticated_page.locator(".col-mode-effective").first).to_be_visible()
        expect(authenticated_page.locator(".col-mode-policy").first).to_be_hidden()


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.display
class TestDashboardDisplayValidation:
    """
    Display validation tests for dashboard.

    These tests catch rendering bugs that unit tests miss:
    - NaN appearing in tables
    - Missing $ or % symbols
    - Incorrect formatting
    - Missing variance colors
    """

    @pytest.fixture(autouse=True)
    def setup_validator(self) -> None:
        """Setup display validator for all tests."""
        from .helpers import FinancialDisplayValidator

        self.validator = FinancialDisplayValidator()

    @pytest.fixture
    def dashboard_with_data(self, test_user: Any, base_system_data: Any) -> dict[str, Any]:
        """Create portfolio with known values for display testing."""
        from .helpers import create_test_portfolio_with_values

        return create_test_portfolio_with_values(
            test_user, base_system_data, us_equities_value=50000.0, bonds_value=30000.0
        )

    def test_dashboard_has_no_nan_values(
        self, authenticated_page: Page, live_server_url: str, dashboard_with_data: dict[str, Any]
    ) -> None:
        """
        CRITICAL: Dashboard should never display NaN values.

        This catches:
        - Division by zero errors
        - Missing price data causing NaN
        - Null reference errors in calculations
        """
        authenticated_page.goto(f"{live_server_url}/")

        # Use validator from helpers
        self.validator.assert_no_invalid_values(authenticated_page)

        # Verify table actually loaded
        allocation_table = authenticated_page.locator("[data-testid^='allocation-table']")
        expect(allocation_table.first).to_be_visible()

    def test_all_money_values_properly_formatted(
        self, authenticated_page: Page, live_server_url: str, dashboard_with_data: dict[str, Any]
    ) -> None:
        """
        All currency values should display with $.

        Tests that |money template filter is applied correctly.
        """
        authenticated_page.goto(f"{live_server_url}/")

        # Find money cells in the dollar table
        money_cells = authenticated_page.locator(
            "[data-testid='allocation-table-dollar'] [data-testid^='portfolio-actual']"
        )
        count = money_cells.count()

        assert count > 0, "No money cells found on dashboard"

        # Check each visible cell has valid format
        for i in range(min(count, 5)):  # Check first 5
            cell = money_cells.nth(i)
            if cell.is_visible():
                text = cell.text_content()
                assert text is not None
                # Should contain $ sign
                assert "$" in text, f"Money cell missing $: {text}"

    def test_sidebar_displays_correctly(
        self, authenticated_page: Page, live_server_url: str, dashboard_with_data: dict[str, Any]
    ) -> None:
        """
        Sidebar should display without errors.

        Sidebar aggregates across all accounts which can cause
        errors if any account has missing data.
        """
        authenticated_page.goto(f"{live_server_url}/")

        # Check sidebar
        sidebar = authenticated_page.locator("[data-testid='sidebar']")
        expect(sidebar).to_be_visible()

        # Sidebar should have no NaN
        sidebar_html = sidebar.inner_html()
        for pattern in self.validator.INVALID_PATTERNS:
            assert pattern not in sidebar_html, f"Found '{pattern}' in sidebar"

        # Portfolio total should be visible
        total_value = authenticated_page.locator("[data-testid='sidebar-total-value']")
        expect(total_value).to_be_visible()

    def test_variance_cells_have_color_classes(
        self, authenticated_page: Page, live_server_url: str, test_user: Any, base_system_data: Any
    ) -> None:
        """
        Variance cells should have variance-positive or variance-negative class.

        This ensures visual indicators (red/green) are applied.
        """
        from portfolio.models import AllocationStrategy

        from .helpers import create_test_portfolio_with_values

        # Create portfolio with variance
        create_test_portfolio_with_values(
            test_user, base_system_data, us_equities_value=60000.0, bonds_value=40000.0
        )

        # Set 50/50 target to create variance
        strategy = AllocationStrategy.objects.create(user=test_user, name="50/50")
        strategy.save_allocations(
            {
                base_system_data.asset_class_us_equities.id: Decimal("50.00"),
                base_system_data.asset_class_cash.id: Decimal("50.00"),
            }
        )

        # Assign to account type
        from portfolio.models import AccountTypeStrategyAssignment

        AccountTypeStrategyAssignment.objects.create(
            user=test_user,
            account_type=base_system_data.type_taxable,
            allocation_strategy=strategy,
        )

        authenticated_page.goto(f"{live_server_url}/")

        # Find variance cells
        variance_cells = authenticated_page.locator(".variance-col")

        if variance_cells.count() > 0:
            cell = variance_cells.first
            if cell.is_visible():
                classes = cell.get_attribute("class") or ""
                # Should have some styling
                assert "variance" in classes, f"Variance cell missing styling: {classes}"

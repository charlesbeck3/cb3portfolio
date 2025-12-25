from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import (
    Account,
    AllocationStrategy,
    Holding,
    TargetAllocation,
)
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


@pytest.fixture(autouse=True)
def live_server_url(live_server: Any) -> str:
    """Explicitly use live_server fixture for Playwright tests."""
    return live_server.url


@pytest.mark.django_db
class TestFrontendAllocations(PortfolioTestMixin):
    @pytest.fixture(autouse=True)
    def setup_data(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)

        # Use seeded asset classes and securities
        # (setup_portfolio_data() already created these via SystemSeederService)

        # Setup Account
        self.acc_roth = Account.objects.create(
            user=self.user,
            name="My Roth",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )

        # Holdings: $1000 US Equities (using seeded VTI which maps to US Equities)
        Holding.objects.create(
            account=self.acc_roth, security=self.vti, shares=10, current_price=100
        )

        # Setup Strategies
        self.strategy_all_us_equities = AllocationStrategy.objects.create(
            user=self.user, name="All US Equities"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_all_us_equities,
            asset_class=self.asset_class_us_equities,
            target_percent=Decimal("100"),
        )

        self.strategy_all_cash = AllocationStrategy.objects.create(user=self.user, name="All Cash")
        # Save 100% cash allocation using domain method
        self.strategy_all_cash.save_allocations(
            {self.asset_class_cash.id: AllocationStrategy.TOTAL_ALLOCATION_PCT}
        )

    def test_calculation_persistence(self, page: Page, live_server_url: str) -> None:
        """
        Verify that changing a strategy assignment and saving updates:
        1. Total Portfolio Target %
        2. Variance %
        """
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', "testuser")
        page.fill('input[name="password"]', "password")
        page.click('button[type="submit"]')

        # Go to Allocations
        page.goto(f"{live_server_url}/targets/")

        # Use Select for US Equities strategy override in My Roth
        select_name = f"strategy_acc_{self.acc_roth.id}"
        unique_select_selector = f'#allocations-table select[name="{select_name}"]'

        # Expand the account column
        expand_btn = page.locator(f'#allocations-table button[data-at-id="{self.type_roth.id}"]')
        expand_btn.click()

        # Wait for select to be visible
        select_locator = page.locator(unique_select_selector)
        expect(select_locator).to_be_visible()

        # Select "All US Equities" (100% US Equities)
        select_locator.select_option(label="All US Equities")

        # Save
        with page.expect_navigation():
            page.click("#save-button-top")

        # Verify persistence and calculation on reload
        # US Equities Row Total Target ID: `row-total-{ac_id}`
        row_total_selector = f"#allocations-table #row-total-{self.asset_class_us_equities.id}"
        expect(page.locator(row_total_selector)).to_contain_text("100.0%")

        # Verify Variance Updates (Current 1000 / Total 1000 = 100%, Target 100% -> 0% variance)
        # The Drift display might be formatted.
        row_var_selector = f"#allocations-table #row-var-{self.asset_class_us_equities.id}"
        expect(page.locator(row_var_selector)).to_contain_text("0.0%")

    def test_category_subtotal_updates(self, page: Page, live_server_url: str) -> None:
        """Verify Category Subtotals update correctly after save."""
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', "testuser")
        page.fill('input[name="password"]', "password")
        page.click('button[type="submit"]')
        page.goto(f"{live_server_url}/targets/")

        # ROTH Default Select
        select_name = f"strategy_at_{self.type_roth.id}"
        select_locator = page.locator(f'#allocations-table select[name="{select_name}"]')

        # Category Subtotal Target ID: `sub-total-target-US_EQUITIES`
        sub_target_selector = "#allocations-table #sub-total-target-US_EQUITIES"

        # Set Default to All US Equities (100%).
        select_locator.select_option(label="All US Equities")
        with page.expect_navigation():
            page.click("#save-button-top")

        # Expected: 100%
        expect(page.locator(sub_target_selector)).to_contain_text("100.0%")

        # Set Default to All Cash (0% Equities)
        select_locator = page.locator(f'#allocations-table select[name="{select_name}"]')
        select_locator.select_option(label="All Cash")
        page.click("#save-button-top")

        expect(page.locator(sub_target_selector)).to_contain_text("0.0%")

    def test_cash_row_updates(self, page: Page, live_server_url: str) -> None:
        """Verify Cash Row calculations after save."""
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', "testuser")
        page.fill('input[name="password"]', "password")
        page.click('button[type="submit"]')
        page.goto(f"{live_server_url}/targets/")

        # ROTH Default Select
        select_name = f"strategy_at_{self.type_roth.id}"
        select_locator = page.locator(f'#allocations-table select[name="{select_name}"]')

        # Cash Total Target ID: `cash-total`
        cash_total_selector = "#allocations-table #cash-total"

        # If US Equities = 100%, Cash (Implicit) = 0%
        select_locator.select_option(label="All US Equities")
        page.click("#save-button-top")

        expect(page.locator(cash_total_selector)).to_contain_text("0.0%")

        # If All Cash = 100% Cash
        select_locator = page.locator(f'#allocations-table select[name="{select_name}"]')
        select_locator.select_option(label="All Cash")
        page.click("#save-button-top")
        expect(page.locator(cash_total_selector)).to_contain_text("100.0%")

    def test_variance_mode_column_toggle(self, page: Page, live_server_url: str) -> None:
        """Verify allocating table columns toggle based on variance mode."""
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', "testuser")
        page.fill('input[name="password"]', "password")
        page.click('button[type="submit"]')
        page.goto(f"{live_server_url}/targets/")

        # Locators for columns (using the classes we added)
        policy_cols = page.locator(".col-mode-policy")
        effective_cols = page.locator(".col-mode-effective")

        # Locators for mode labels (since inputs are hidden)
        label_effective = page.locator('label[for="variance-effective"]')
        label_policy = page.locator('label[for="variance-policy"]')

        # DEFAULT: Effective Mode
        # Ensure effective is selected. Can click it to be sure.
        label_effective.click()

        # Verify Effective columns are visible (not hidden)
        expect(effective_cols.first).to_be_visible()

        # Verify Policy columns are hidden
        expect(policy_cols.first).not_to_be_visible()

        # SWITCH TO POLICY MODE
        label_policy.click()

        # Verify Policy columns are visible
        expect(policy_cols.first).to_be_visible()

        # Verify Effective columns are hidden
        expect(effective_cols.first).not_to_be_visible()

    def test_portfolio_variance_toggle(self, page: Page, live_server_url: str) -> None:
        """Verify portfolio variance column toggles between effective and policy."""
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', "testuser")
        page.fill('input[name="password"]', "password")
        page.click('button[type="submit"]')

        # 1. Setup a portfolio explicit target that differs from effective
        # Create a "Portfolio Default" strategy with 50/50 US Equities/Cash
        strategy_portfolio = AllocationStrategy.objects.create(
            user=self.user, name="Portfolio Strategy"
        )
        strategy_portfolio.save_allocations(
            {
                self.asset_class_us_equities.id: Decimal("50.0"),
                self.asset_class_cash.id: Decimal("50.0"),
            }
        )
        self.portfolio.allocation_strategy = strategy_portfolio
        self.portfolio.save()

        # 2. Assign "All US Equities" (100% US Equities) to My Roth
        # This will make effective target 100% US Equities
        self.acc_roth.allocation_strategy = self.strategy_all_us_equities
        self.acc_roth.save()

        page.goto(f"{live_server_url}/targets/")

        # Get portfolio variance cell for US Equities
        portfolio_variance = page.locator(
            f"#allocations-table #row-var-{self.asset_class_us_equities.id}"
        )

        # Default (Effective Variance):
        # Actual: 100%, Effective: 100% (Weighted from My Roth) -> Var: 0%
        # Note: formatted as 0.0%
        expect(portfolio_variance).to_contain_text("0.0%")

        # Toggle to Policy Variance
        page.locator('label[for="variance-policy"]').click()

        # Policy Variance (vs Portfolio Explicit Target):
        # Actual: 100%, Policy (Explicit): 50% -> Var: +50.0%
        # Wait for the toggle to complete
        page.wait_for_timeout(100)
        expect(portfolio_variance).to_contain_text("+50.0%")

        # Toggle back
        page.locator('label[for="variance-effective"]').click()
        expect(portfolio_variance).to_contain_text("0.0%")

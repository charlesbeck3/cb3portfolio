from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import (
    Account,
    AllocationStrategy,
    AssetClass,
    AssetClassCategory,
    Holding,
    Security,
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

        # Setup Assets
        self.cat_eq, _ = AssetClassCategory.objects.get_or_create(
            code="EQUITIES", defaults={"label": "Equities", "sort_order": 1}
        )
        self.ac_us, _ = AssetClass.objects.get_or_create(
            name="US Stocks", defaults={"category": self.cat_eq}
        )
        self.ac_cash, _ = AssetClass.objects.get_or_create(
            name="Cash", defaults={"category": self.cat_cash}
        )
        self.ac_intl, _ = AssetClass.objects.get_or_create(
            name="Intl Stocks", defaults={"category": self.cat_eq}
        )
        self.sec_vxus, _ = Security.objects.get_or_create(
            ticker="VXUS", defaults={"name": "VXUS", "asset_class": self.ac_intl}
        )
        self.sec_vti, _ = Security.objects.get_or_create(
            ticker="VTI", defaults={"name": "VTI", "asset_class": self.ac_us}
        )

        # Setup Account
        self.acc_roth = Account.objects.create(
            user=self.user,
            name="My Roth",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )

        # Holdings: $1000 US Stocks
        Holding.objects.create(
            account=self.acc_roth, security=self.sec_vti, shares=10, current_price=100
        )

        # Setup Strategies
        self.strategy_all_stocks = AllocationStrategy.objects.create(
            user=self.user, name="All Stocks"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_all_stocks, asset_class=self.ac_us, target_percent=Decimal("100")
        )

        self.strategy_all_cash = AllocationStrategy.objects.create(user=self.user, name="All Cash")
        # Save 100% cash allocation using domain method
        self.strategy_all_cash.save_allocations(
            {self.ac_cash.id: AllocationStrategy.TOTAL_ALLOCATION_PCT}
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

        # Use Select for US Stocks strategy override in My Roth
        select_name = f"strategy_acc_{self.acc_roth.id}"
        unique_select_selector = f'#allocations-table select[name="{select_name}"]'

        # Expand the account column
        expand_btn = page.locator(f'#allocations-table button[data-at-id="{self.type_roth.id}"]')
        expand_btn.click()

        # Wait for select to be visible
        select_locator = page.locator(unique_select_selector)
        expect(select_locator).to_be_visible()

        # Select "All Stocks" (100% US Stocks)
        select_locator.select_option(label="All Stocks")

        # Save
        with page.expect_navigation():
            page.click("#save-button-top")

        # Verify persistence and calculation on reload
        # US Stocks Row Total Target ID: `row-total-{ac_id}`
        row_total_selector = f"#allocations-table #row-total-{self.ac_us.id}"
        expect(page.locator(row_total_selector)).to_contain_text("100.0%")

        # Verify Variance Updates (Current 1000 / Total 1000 = 100%, Target 100% -> 0% variance)
        # The Drift display might be formatted.
        row_var_selector = f"#allocations-table #row-var-{self.ac_us.id}"
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

        # Category Subtotal Target ID: `sub-total-target-EQUITIES`
        sub_target_selector = "#allocations-table #sub-total-target-EQUITIES"

        # Set Default to All Stocks (100%).
        select_locator.select_option(label="All Stocks")
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

        # If US Stocks = 100%, Cash (Implicit) = 0%
        select_locator.select_option(label="All Stocks")
        page.click("#save-button-top")

        expect(page.locator(cash_total_selector)).to_contain_text("0.0%")

        # If All Cash = 100% Cash
        select_locator = page.locator(f'#allocations-table select[name="{select_name}"]')
        select_locator.select_option(label="All Cash")
        page.click("#save-button-top")
        expect(page.locator(cash_total_selector)).to_contain_text("100.0%")

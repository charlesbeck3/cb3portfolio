from decimal import Decimal
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import AllocationStrategy, TargetAllocation


@pytest.mark.django_db
class TestFrontendAllocations:
    @pytest.fixture(autouse=True)
    def setup_data(self, simple_holdings: dict[str, Any]) -> None:
        self.user = simple_holdings["user"]
        self.portfolio = simple_holdings["portfolio"]
        self.acc_roth = simple_holdings["account"]
        self.system = simple_holdings["system"]

        # Use existing asset classes from system
        self.asset_class_us_equities = self.system.asset_class_us_equities
        self.asset_class_cash = self.system.asset_class_cash
        self.type_roth = self.system.type_roth

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
        self.strategy_all_cash.save_allocations(
            {self.asset_class_cash.id: AllocationStrategy.TOTAL_ALLOCATION_PCT}
        )

    def test_calculation_persistence(self, authenticated_page: Page, live_server_url: str) -> None:
        """Verify that changing a strategy assignment and saving updates correctly."""
        authenticated_page.goto(f"{live_server_url}/targets/")

        # Use Select for US Equities strategy override in My Roth
        select_name = f"strategy_acc_{self.acc_roth.id}"
        unique_select_selector = f'#allocations-table select[name="{select_name}"]'

        # Expand the account column
        expand_btn = authenticated_page.locator(
            f'#allocations-table button[data-at-id="{self.type_roth.id}"]'
        )
        expand_btn.click()

        # Wait for select to be visible
        select_locator = authenticated_page.locator(unique_select_selector)
        expect(select_locator).to_be_visible()

        # Select "All US Equities" (100% US Equities)
        select_locator.select_option(label="All US Equities")

        # Save
        with authenticated_page.expect_navigation():
            authenticated_page.click("#save-button-top")

        # Verify persistence and calculation on reload
        row_total_selector = f"#allocations-table #row-total-{self.asset_class_us_equities.id}"
        expect(authenticated_page.locator(row_total_selector)).to_contain_text("100.0%")

        row_var_selector = f"#allocations-table #row-var-{self.asset_class_us_equities.id}"
        expect(authenticated_page.locator(row_var_selector)).to_contain_text("0.0%")

    def test_category_subtotal_updates(
        self, authenticated_page: Page, live_server_url: str
    ) -> None:
        """Verify Category Subtotals update correctly after save."""
        authenticated_page.goto(f"{live_server_url}/targets/")

        # ROTH Default Select
        select_name = f"strategy_at_{self.type_roth.id}"
        select_locator = authenticated_page.locator(
            f'#allocations-table select[name="{select_name}"]'
        )

        # Category Subtotal Target ID: `sub-total-target-US_EQUITIES`
        sub_target_selector = "#allocations-table #sub-total-target-US_EQUITIES"

        # Set Default to All US Equities (100%).
        select_locator.select_option(label="All US Equities")
        with authenticated_page.expect_navigation():
            authenticated_page.click("#save-button-top")

        expect(authenticated_page.locator(sub_target_selector)).to_contain_text("100.0%")

        # Set Default to All Cash (0% Equities)
        select_locator = authenticated_page.locator(
            f'#allocations-table select[name="{select_name}"]'
        )
        select_locator.select_option(label="All Cash")
        authenticated_page.click("#save-button-top")

        expect(authenticated_page.locator(sub_target_selector)).to_contain_text("0.0%")

    def test_cash_row_updates(self, authenticated_page: Page, live_server_url: str) -> None:
        """Verify Cash Row calculations after save."""
        authenticated_page.goto(f"{live_server_url}/targets/")

        # ROTH Default Select
        select_name = f"strategy_at_{self.type_roth.id}"
        select_locator = authenticated_page.locator(
            f'#allocations-table select[name="{select_name}"]'
        )

        # Cash Total Target ID: `cash-total`
        cash_total_selector = "#allocations-table #cash-total"

        # If US Equities = 100%, Cash (Implicit) = 0%
        select_locator.select_option(label="All US Equities")
        authenticated_page.click("#save-button-top")

        expect(authenticated_page.locator(cash_total_selector)).to_contain_text("0.0%")

        # If All Cash = 100% Cash
        select_locator = authenticated_page.locator(
            f'#allocations-table select[name="{select_name}"]'
        )
        select_locator.select_option(label="All Cash")
        authenticated_page.click("#save-button-top")
        expect(authenticated_page.locator(cash_total_selector)).to_contain_text("100.0%")

    def test_variance_mode_column_toggle(
        self, authenticated_page: Page, live_server_url: str
    ) -> None:
        """Verify allocating table columns toggle based on variance mode."""
        authenticated_page.goto(f"{live_server_url}/targets/")

        # Locators for columns
        policy_cols = authenticated_page.locator(".col-mode-policy")
        effective_cols = authenticated_page.locator(".col-mode-effective")

        # Locators for mode labels
        label_effective = authenticated_page.locator('label[for="variance-effective"]')
        label_policy = authenticated_page.locator('label[for="variance-policy"]')

        # DEFAULT: Effective Mode
        label_effective.click()
        expect(effective_cols.first).to_be_visible()
        expect(policy_cols.first).not_to_be_visible()

        # SWITCH TO POLICY MODE
        label_policy.click()
        expect(policy_cols.first).to_be_visible()
        expect(effective_cols.first).not_to_be_visible()

    def test_portfolio_variance_toggle(
        self, authenticated_page: Page, live_server_url: str
    ) -> None:
        """Verify portfolio variance column toggles between effective and policy."""
        # 1. Setup a portfolio explicit target that differs from effective
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
        self.acc_roth.allocation_strategy = self.strategy_all_us_equities
        self.acc_roth.save()

        authenticated_page.goto(f"{live_server_url}/targets/")

        # Get portfolio variance cell for US Equities
        portfolio_variance = authenticated_page.locator(
            f"#allocations-table #row-var-{self.asset_class_us_equities.id}"
        )

        # Default (Effective Variance): Var: 0.0%
        expect(portfolio_variance).to_contain_text("0.0%")

        # Toggle to Policy Variance
        authenticated_page.locator('label[for="variance-policy"]').click()

        # Policy Variance (vs Portfolio Explicit Target): Var: +50.0%
        authenticated_page.wait_for_timeout(100)
        expect(portfolio_variance).to_contain_text("50.0%")

        # Toggle back
        authenticated_page.locator('label[for="variance-effective"]').click()
        expect(portfolio_variance).to_contain_text("0.0%")

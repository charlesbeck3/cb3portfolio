from django.contrib.auth import get_user_model

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import Account, AssetCategory, AssetClass, Holding, Security

from .base import PortfolioTestMixin

User = get_user_model()

@pytest.fixture(autouse=True)
def live_server_url(live_server):
    """Explicitly use live_server fixture for Playwright tests."""
    return live_server.url

@pytest.mark.django_db
class TestFrontendAllocations(PortfolioTestMixin):
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username='testuser', password='password')

        # Setup Assets
        self.cat_eq, _ = AssetCategory.objects.get_or_create(code='EQUITIES', defaults={'label': 'Equities', 'sort_order': 1})
        self.ac_us, _ = AssetClass.objects.get_or_create(name='US Stocks', defaults={'category': self.cat_eq})
        self.sec_vti, _ = Security.objects.get_or_create(ticker='VTI', defaults={'name': 'VTI', 'asset_class': self.ac_us})

        # Setup Account
        self.acc_roth = Account.objects.create(
            user=self.user,
            name='My Roth',
            account_type=self.type_roth,
            institution=self.institution
        )

        # Holdings: $1000 US Stocks
        Holding.objects.create(account=self.acc_roth, security=self.sec_vti, shares=10, current_price=100)

    def test_interactive_calculation(self, page: Page, live_server_url):
        """
        Verify that changing an override input dynamically updates:
        1. Total Portfolio Target %
        2. Variance %
        """
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', 'testuser')
        page.fill('input[name="password"]', 'password')
        page.click('button[type="submit"]')

        # Go to Allocations
        page.goto(f"{live_server_url}/targets/")

        # Find the input for US Stocks override in My Roth
        # Structure: Override inputs have `name="target_account_{acc_id}_{ac_id}"`
        input_name = f"target_account_{self.acc_roth.id}_{self.ac_us.id}"
        unique_input_selector = f'input[name="{input_name}"]'

        # Expand the account column if needed (it's hidden by default for individual accounts)
        # But wait, override inputs are in the hidden columns?
        # Yes, `d-none col-acc-...`. We need to click expand button first.

        # Click expand button for Roth (Account Type)
        expand_btn = page.locator(f'button[data-at-id="{self.type_roth.id}"]')
        expand_btn.click()

        # Wait for column to be visible
        input_locator = page.locator(unique_input_selector)
        expect(input_locator).to_be_visible()

        # Initial State: Default is likely 0 or whatever.
        # Enter 50%
        input_locator.fill('50')

        # Trigger change event? The script listens to 'input'. Playwright fill triggers standard events.

        # Verify Total Portfolio Target Updates
        # US Stocks Row Total Target ID: `row-total-{ac_id}`
        # If Roth is 100% of portfolio ($1000/$1000), and we set Roth Target for US to 50%.
        # Then Portfolio Target for US = 50% * (Roth Value / Total Value) = 50% * 1 = 50%.

        row_total_selector = f'#row-total-{self.ac_us.id}'
        expect(page.locator(row_total_selector)).to_have_text('50.0%')

        # Verify Variance Updates
        # Current is 100% (since we hold $1000 VTI).
        # Variance = Current (100) - Target (50) = +50%
        row_var_selector = f'#row-var-{self.ac_us.id}'
        expect(page.locator(row_var_selector)).to_have_text('50.0%')

        # Enter 100%
        input_locator.fill('100')
        expect(page.locator(row_total_selector)).to_have_text('100.0%')
        expect(page.locator(row_var_selector)).to_have_text('0.0%')

    def test_category_subtotal_updates(self, page: Page, live_server_url):
        """Verify Category Subtotals update dynamically."""
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', 'testuser')
        page.fill('input[name="password"]', 'password')
        page.click('button[type="submit"]')
        page.goto(f"{live_server_url}/targets/")

        # Find US Stocks Default Input (Account Type level)
        # We can test defaults too.
        # ROTH Default Input
        input_name = f"target_{self.type_roth.id}_{self.ac_us.id}"
        input_locator = page.locator(f'input[name="{input_name}"]')

        # US Stocks is in "EQUITIES" category.
        # Category Subtotal Target ID: `sub-total-target-EQUITIES`
        sub_target_selector = '#sub-total-target-EQUITIES'

        # Set Default to 60%
        input_locator.fill('60')

        # Expected: 60% (since Roth is 100% of portfolio)
        expect(page.locator(sub_target_selector)).to_have_text('60.0%')

        # Set Default to 80%
        input_locator.fill('80')
        expect(page.locator(sub_target_selector)).to_have_text('80.0%')

    def test_cash_row_updates(self, page: Page, live_server_url):
        """Verify Cash Row calculations."""
        # Login
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', 'testuser')
        page.fill('input[name="password"]', 'password')
        page.click('button[type="submit"]')
        page.goto(f"{live_server_url}/targets/")

        # ROTH Default Input for US Stocks
        input_name = f"target_{self.type_roth.id}_{self.ac_us.id}"
        input_locator = page.locator(f'input[name="{input_name}"]')

        # Cash Total Target ID: `cash-total`
        cash_total_selector = '#cash-total'

        # If US Stocks = 60%, Cash (Implicit) = 40%
        input_locator.fill('60')

        # Allow slight delay or retry for calculation? Playwright expects usually handles this.
        expect(page.locator(cash_total_selector)).to_have_text('40.0%')

        # If US Stocks = 90%, Cash = 10%
        input_locator.fill('90')
        expect(page.locator(cash_total_selector)).to_have_text('10.0%')

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import Account, AssetClass, Holding

from ..base import PortfolioTestMixin

User = get_user_model()


@pytest.fixture(autouse=True)
def live_server_url(live_server: Any) -> str:
    return live_server.url


def _login(page: Page, live_server_url: str, username: str, password: str) -> None:
    page.goto(f"{live_server_url}/accounts/login/")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')


@pytest.mark.django_db
class TestDashboardPage(PortfolioTestMixin):
    @pytest.fixture(autouse=True)
    def setup_data(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)

        self.us_stocks = AssetClass.objects.create(name="US Stocks", category=self.cat_us_eq)
        self.vti.asset_class = self.us_stocks
        self.vti.save()

        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        Holding.objects.create(
            account=self.account,
            security=self.vti,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )

    def test_variance_mode_toggle(self, page: Page, live_server_url: str) -> None:
        _login(page, live_server_url, "testuser", "password")
        page.goto(f"{live_server_url}/")

        # Default is Effective Variance
        expect(page.locator(".col-mode-effective").first).to_be_visible()
        expect(page.locator(".col-mode-policy").first).to_be_hidden()

        # Switch to Policy Variance (Click the label)
        page.locator('label[for="variance-policy"]').click()

        # Verify columns toggled
        expect(page.locator(".col-mode-policy").first).to_be_visible()
        expect(page.locator(".col-mode-effective").first).to_be_hidden()

        # Switch back to Effective Variance
        page.locator('label[for="variance-effective"]').click()
        expect(page.locator(".col-mode-effective").first).to_be_visible()
        expect(page.locator(".col-mode-policy").first).to_be_hidden()

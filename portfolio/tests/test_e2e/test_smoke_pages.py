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
class TestSmokePages(PortfolioTestMixin):
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

    def test_dashboard_loads(self, page: Page, live_server_url: str) -> None:
        _login(page, live_server_url, "testuser", "password")
        page.goto(f"{live_server_url}/")
        expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

    def test_holdings_page_loads(self, page: Page, live_server_url: str) -> None:
        _login(page, live_server_url, "testuser", "password")
        page.goto(f"{live_server_url}/holdings/")
        expect(page.get_by_role("heading", name="Holdings")).to_be_visible()

    def test_targets_page_loads(self, page: Page, live_server_url: str) -> None:
        _login(page, live_server_url, "testuser", "password")
        page.goto(f"{live_server_url}/targets/")
        expect(page.get_by_role("heading", name="Allocations")).to_be_visible()

    def test_account_holdings_page_loads(self, page: Page, live_server_url: str) -> None:
        _login(page, live_server_url, "testuser", "password")
        page.goto(f"{live_server_url}/account/{self.account.id}/")
        expect(
            page.get_by_role("heading", name=f"Holdings for {self.account.name}")
        ).to_be_visible()

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest
from playwright.sync_api import Page

from portfolio.models import Account, Holding
from portfolio.tests.constants import TEST_PASSWORD, TEST_USERNAME


@pytest.fixture(autouse=True)
def live_server_url(live_server: Any) -> str:
    """Explicitly use live_server fixture for Playwright tests."""
    return live_server.url


@pytest.fixture
def login_user(page: Page, live_server_url: str) -> Callable[..., None]:
    """Fixture that provides a login function."""

    def _login(username: str = TEST_USERNAME, password: str = TEST_PASSWORD) -> None:
        page.goto(f"{live_server_url}/accounts/login/")
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

    return _login


@pytest.fixture
def authenticated_page(page: Page, login_user: Callable[..., None]) -> Page:
    """Fixture that provides a page with user already logged in."""
    login_user()
    return page


@pytest.fixture
def standard_test_portfolio(db: Any) -> dict[str, Any]:
    """
    Creates a standard test portfolio with:
    - One user (testuser/password)
    - One portfolio
    - One Roth IRA account with $1000 VTI holdings

    Returns dict with all created objects for easy access.
    """
    from portfolio.tests.base import PortfolioTestMixin

    mixin = PortfolioTestMixin()
    mixin.setup_system_data()

    user_model = get_user_model()
    user = user_model.objects.create_user(username=TEST_USERNAME, password=TEST_PASSWORD)
    mixin.create_portfolio(user=user)

    us_stocks = mixin.asset_class_us_equities

    account = Account.objects.create(
        user=user,
        name="Roth IRA",
        portfolio=mixin.portfolio,
        account_type=mixin.type_roth,
        institution=mixin.institution,
    )

    holding = Holding.objects.create(
        account=account,
        security=mixin.vti,
        shares=Decimal("10"),
        current_price=Decimal("100"),
    )

    return {
        "mixin": mixin,
        "user": user,
        "portfolio": mixin.portfolio,
        "us_stocks": us_stocks,
        "account": account,
        "holding": holding,
    }

from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page

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

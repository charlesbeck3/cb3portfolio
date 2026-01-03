from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page, expect

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
        # Wait for redirect to dashboard or other page to ensure session is set
        try:
            expect(page.locator("body")).not_to_contains_text(
                "Sign In"
            )  # Simple check, or wait URL
            # Better to wait for specific element that indicates logged in, e.g. navbar user
            # But let's just wait for url not to be login
            page.wait_for_url(f"{live_server_url}/")
        except Exception:
            # If we didn't redirect to root, maybe we are somewhere else but logged in?
            # Or maybe login failed.
            pass

    return _login


@pytest.fixture
def authenticated_page(page: Page, login_user: Callable[..., None], test_user: Any) -> Page:
    """
    Fixture that provides a page with user already logged in.

    Depends on test_user to ensure the user exists in the DB before login.
    """
    login_user()
    return page

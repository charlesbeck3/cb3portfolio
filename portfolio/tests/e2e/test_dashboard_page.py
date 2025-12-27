from typing import Any

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.django_db
class TestDashboardPage:
    @pytest.fixture(autouse=True)
    def setup_data(self, standard_test_portfolio: dict[str, Any]) -> None:
        self.data = standard_test_portfolio

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

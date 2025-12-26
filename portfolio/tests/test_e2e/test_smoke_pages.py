from typing import Any

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.django_db
class TestSmokePages:
    @pytest.fixture(autouse=True)
    def setup_data(self, standard_test_portfolio: dict[str, Any]) -> None:
        self.data = standard_test_portfolio
        self.account = self.data["account"]

    def test_dashboard_loads(self, authenticated_page: Page, live_server_url: str) -> None:
        authenticated_page.goto(f"{live_server_url}/")
        expect(authenticated_page.get_by_role("heading", name="Dashboard")).to_be_visible()

    def test_holdings_page_loads(self, authenticated_page: Page, live_server_url: str) -> None:
        authenticated_page.goto(f"{live_server_url}/holdings/")
        expect(authenticated_page.get_by_role("heading", name="Holdings")).to_be_visible()

    def test_targets_page_loads(self, authenticated_page: Page, live_server_url: str) -> None:
        authenticated_page.goto(f"{live_server_url}/targets/")
        expect(authenticated_page.get_by_role("heading", name="Allocations")).to_be_visible()

    def test_account_holdings_page_loads(
        self, authenticated_page: Page, live_server_url: str
    ) -> None:
        authenticated_page.goto(f"{live_server_url}/account/{self.account.id}/")
        expect(
            authenticated_page.get_by_role("heading", name=f"Holdings for {self.account.name}")
        ).to_be_visible()

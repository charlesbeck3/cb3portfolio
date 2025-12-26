import re
from decimal import Decimal
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import AllocationStrategy


@pytest.mark.django_db
class TestPortfolioExplicitTarget:
    @pytest.fixture(autouse=True)
    def setup_data(self, standard_test_portfolio: dict[str, Any]) -> None:
        self.data = standard_test_portfolio
        self.user = self.data["user"]
        self.portfolio = self.data["portfolio"]
        self.acc_roth = self.data["account"]
        self.mixin = self.data["mixin"]

        # Asset classes from mixin
        self.ac_us_eq = self.mixin.asset_class_us_equities
        self.ac_treasuries_short = self.mixin.asset_class_treasuries_short

        # Setup Portfolio Strategy (Explicit Target)
        self.strategy_balanced = AllocationStrategy.objects.create(
            user=self.user, name="60/40 Balanced"
        )
        self.strategy_balanced.save_allocations(
            {self.ac_us_eq.id: Decimal("60.00"), self.ac_treasuries_short.id: Decimal("40.00")}
        )
        self.portfolio.allocation_strategy = self.strategy_balanced
        self.portfolio.save()

        # Setup Account Strategy (Weighted Target)
        self.strategy_all_stocks = AllocationStrategy.objects.create(
            user=self.user, name="All Stocks"
        )
        self.strategy_all_stocks.save_allocations({self.ac_us_eq.id: Decimal("100.00")})
        self.acc_roth.allocation_strategy = self.strategy_all_stocks
        self.acc_roth.save()

    def test_portfolio_target_columns_presence(
        self, authenticated_page: Page, live_server_url: str
    ) -> None:
        """Verify that Total Portfolio columns include basic and variance columns."""
        authenticated_page.goto(f"{live_server_url}/targets/")

        # Check "Total Portfolio" header
        portfolio_header = authenticated_page.locator("#allocations-table th").filter(
            has_text=re.compile(r"Total Portfolio")
        )
        expect(portfolio_header).to_be_visible()

        # Sub-headers for Total Portfolio section (Actual, Policy, Effective, Variance)
        sub_headers = (
            authenticated_page.locator("#allocations-table thead tr")
            .nth(1)
            .locator("th.table-active")
        )

        # New behavior: Actual, Policy, Effective, Variance (4 columns)
        expect(sub_headers).to_have_count(4)

        texts = [sub_headers.nth(i).inner_text().strip() for i in range(4)]
        assert "Actual" in texts
        assert "Policy" in texts
        assert "Effective" in texts
        assert "Variance" in texts

    def test_portfolio_target_values(self, authenticated_page: Page, live_server_url: str) -> None:
        """Verify that values in Policy and Effective targets are correct."""
        authenticated_page.goto(f"{live_server_url}/targets/")

        # Find the row specifically for "US Equities"
        us_eq_row = authenticated_page.locator("#allocations-table tbody tr").filter(
            has=authenticated_page.locator("td").first.filter(has_text=re.compile(r"^US Equities$"))
        )

        # Expect 4 cells in the table-active (portfolio) section
        portfolio_cells = us_eq_row.locator("td.table-active")
        expect(portfolio_cells).to_have_count(4)

        # Actual: 100.0%
        expect(portfolio_cells.nth(0)).to_contain_text("100.0%")
        # Policy: 60.0%
        expect(portfolio_cells.nth(1)).to_contain_text("60.0%")
        # Effective: 100.0%
        expect(portfolio_cells.nth(2)).to_contain_text("100.0%")
        # Variance: 0.0%
        expect(portfolio_cells.nth(3)).to_contain_text("0.0%")

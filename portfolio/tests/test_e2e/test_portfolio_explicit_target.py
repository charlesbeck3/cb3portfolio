import re
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import AllocationStrategy, Holding
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


@pytest.mark.django_db
class TestPortfolioExplicitTarget(PortfolioTestMixin):
    @pytest.fixture(autouse=True)
    def setup_data(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)

        # Setup Account
        from portfolio.models import Account
        self.acc_roth = Account.objects.create(
            user=self.user,
            name="My Roth",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )

        # Holdings: $1000 US Stocks
        Holding.objects.create(
            account=self.acc_roth, security=self.vti, shares=10, current_price=100
        )

        # Setup Portfolio Strategy (Explicit Target)
        self.strategy_balanced = AllocationStrategy.objects.create(
            user=self.user, name="60/40 Balanced"
        )
        self.strategy_balanced.save_allocations({
            self.ac_us_eq.id: Decimal("60.00"),
            self.ac_treasuries_short.id: Decimal("40.00")
        })
        self.portfolio.allocation_strategy = self.strategy_balanced
        self.portfolio.save()

        # Setup Account Strategy (Weighted Target)
        self.strategy_all_stocks = AllocationStrategy.objects.create(
            user=self.user, name="All Stocks"
        )
        self.strategy_all_stocks.save_allocations({
            self.ac_us_eq.id: Decimal("100.00")
        })
        self.acc_roth.allocation_strategy = self.strategy_all_stocks
        self.acc_roth.save()

    def test_portfolio_target_columns_presence(self, page: Page, live_server: Any) -> None:
        """Verify that Total Portfolio columns include both Exp. Target and Wt. Target."""
        # login
        page.goto(f"{live_server.url}/accounts/login/")
        page.fill('input[name="username"]', "testuser")
        page.fill('input[name="password"]', "password")
        page.click('button[type="submit"]')

        # Go to targets
        page.goto(f"{live_server.url}/targets/")

        # Check "Total Portfolio" header
        portfolio_header = page.locator('#allocations-table th').filter(has_text=re.compile(r"Total Portfolio"))
        expect(portfolio_header).to_be_visible()

        # Sub-headers for Total Portfolio section (Current, Exp. Target, Wt. Target, Drift)
        sub_headers = page.locator('#allocations-table thead tr').nth(1).locator('th.table-active')

        # New behavior: Current, Exp. Target, Wt. Target, Drift (4 columns)
        expect(sub_headers).to_have_count(4)

        texts = [sub_headers.nth(i).inner_text().strip() for i in range(4)]
        assert "Current" in texts
        assert "Exp. Target" in texts
        assert "Wt. Target" in texts
        assert "Drift" in texts

    def test_portfolio_target_values(self, page: Page, live_server: Any) -> None:
        """Verify that values in Exp. Target and Wt. Target are correct."""
        # login
        page.goto(f"{live_server.url}/accounts/login/")
        page.fill('input[name="username"]', "testuser")
        page.fill('input[name="password"]', "password")
        page.click('button[type="submit"]')

        # Go to targets
        page.goto(f"{live_server.url}/targets/")

        # US Equities row
        # Weighted target should be 100% (from All Stocks strategy)
        # Explicit target should be 60% (from Balanced strategy)

        # Find the row specifically for "US Equities"
        us_eq_row = page.locator('#allocations-table tbody tr').filter(
            has=page.locator('td').first.filter(has_text=re.compile(r'^US Equities$'))
        )

        # Expect 4 cells in the table-active (portfolio) section
        portfolio_cells = us_eq_row.locator('td.table-active')
        expect(portfolio_cells).to_have_count(4)

        # Current: 100.0%
        expect(portfolio_cells.nth(0)).to_contain_text("100.0%")
        # Exp. Target: 60.0%
        expect(portfolio_cells.nth(1)).to_contain_text("60.0%")
        # Wt. Target: 100.0%
        expect(portfolio_cells.nth(2)).to_contain_text("100.0%")
        # Drift: 0.0%
        expect(portfolio_cells.nth(3)).to_contain_text("0.0%")

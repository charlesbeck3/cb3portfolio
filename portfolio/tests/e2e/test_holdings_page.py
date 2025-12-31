from django.urls import reverse

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import Account, Holding


@pytest.mark.e2e
def test_holdings_click_interaction(
    page: Page, live_server, test_user, base_system_data, login_user
):
    """Test clicking a holdings row expands details."""

    # Setup data
    from portfolio.models import Portfolio as PortfolioModel

    portfolio = PortfolioModel.objects.create(user=test_user, name="E2E Portfolio")

    acc = Account.objects.create(
        user=test_user,
        name="E2E Account",
        portfolio=portfolio,
        account_type=base_system_data.type_roth,
        institution=base_system_data.institution,
    )

    vti = base_system_data.vti
    Holding.objects.create(account=acc, security=vti, shares=10)

    # Login
    login_user()

    # Go to holdings
    page.goto(f"{live_server.url}{reverse('portfolio:holdings')}")

    # Verify row exists
    ticker_row = page.locator(f"tr[data-ticker='{vti.ticker}']")
    expect(ticker_row).to_be_visible()

    # Click row
    ticker_row.click()

    # Verify details expanded
    details_row = page.locator(f"#ticker-details-{vti.ticker}")
    expect(details_row).to_be_visible()
    expect(details_row.locator("text=Account Level Details")).to_be_visible()
    expect(details_row.locator("text=E2E Account")).to_be_visible()

    # Click again to collapse
    ticker_row.click()

    # Verify details gone (or hidden)
    # My JS removes it and replaces with d-none placeholder
    expect(details_row.locator("text=Account Level Details")).not_to_be_visible()
    expect(details_row).to_have_class("d-none")  # Checks the placeholder has d-none

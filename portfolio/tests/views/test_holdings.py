"""
Tests for holdings view and modifications.

Tests: portfolio/views/holdings.py
"""

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.urls import reverse

import pytest

from portfolio.models import Account, Holding

User = get_user_model()


@pytest.mark.views
@pytest.mark.integration
class TestHoldingsViewHTTP:
    """Test HTTP behavior of HoldingsView (GET)."""

    def test_holdings_view(self, client: Any, test_portfolio: dict[str, Any]) -> None:
        user = test_portfolio["user"]
        client.force_login(user)

        url = reverse("portfolio:holdings")
        response = client.get(url)
        assert response.status_code == 200
        assert "holdings_rows" in response.context
        assert "sidebar_data" in response.context
        assert "account" not in response.context

    def test_holdings_view_with_account(self, client: Any, test_portfolio: dict[str, Any]) -> None:
        user = test_portfolio["user"]
        portfolio = test_portfolio["portfolio"]
        system = test_portfolio["system"]
        client.force_login(user)

        account = Account.objects.create(
            user=user,
            name="My Roth",
            portfolio=portfolio,
            account_type=system.type_roth,
            institution=system.institution,
        )

        url = reverse("portfolio:account_holdings", args=[account.id])
        response = client.get(url)
        assert response.status_code == 200
        assert "account" in response.context
        assert response.context["account"] == account

    def test_holdings_view_invalid_account(self, client: Any, test_user: Any) -> None:
        client.force_login(test_user)
        url = reverse("portfolio:account_holdings", args=[99999])
        response = client.get(url)
        assert response.status_code == 200
        assert "account" not in response.context


@pytest.mark.views
@pytest.mark.integration
class TestHoldingsViewPost:
    """Tests for adding, updating, and deleting holdings (POST)."""

    @pytest.fixture
    def setup_view(self, client, test_user, base_system_data):
        from portfolio.models import Portfolio as PortfolioModel

        system = base_system_data
        portfolio = PortfolioModel.objects.create(user=test_user, name="Holdings Test Portfolio")
        client.force_login(test_user)

        account = Account.objects.create(
            user=test_user,
            name="My Roth",
            portfolio=portfolio,
            account_type=system.type_roth,
            institution=system.institution,
        )

        # Security VTI is available in system data
        sec_vti = system.vti

        return {
            "client": client,
            "user": test_user,
            "account": account,
            "security": sec_vti,
            "system": system,
        }

    def test_add_holding_success(self, setup_view):
        """Verify successful addition of a new holding."""
        setup = setup_view
        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {"security_id": setup["security"].id, "initial_shares": "10.00"}
        response = setup["client"].post(url, data, follow=True)

        assert f"Added {setup['security'].ticker} to account." in response.content.decode()
        holding = Holding.objects.get(account=setup["account"], security=setup["security"])
        assert holding.shares == Decimal("10.00")

    def test_add_holding_existing_warning(self, setup_view):
        """Verify warning when attempting to add duplicate holding."""
        setup = setup_view
        Holding.objects.create(account=setup["account"], security=setup["security"], shares=5)

        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {"security_id": setup["security"].id, "initial_shares": "10.00"}
        response = setup["client"].post(url, data, follow=True)

        assert f"Holding for {setup['security'].ticker} already exists" in response.content.decode()
        holding = Holding.objects.get(account=setup["account"], security=setup["security"])
        assert holding.shares == Decimal("5.00")

    def test_add_holding_invalid_form(self, setup_view):
        """Verify form validation errors."""
        setup = setup_view
        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {"security_id": setup["security"].id}  # Missing shares
        response = setup["client"].post(url, data, follow=True)

        assert "This field is required" in response.content.decode()

    def test_delete_holding(self, setup_view):
        """Verify successful deletion of a holding."""
        setup = setup_view
        Holding.objects.create(account=setup["account"], security=setup["security"], shares=5)

        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {"delete_ticker": setup["security"].ticker}
        response = setup["client"].post(url, data, follow=True)

        assert f"Removed {setup['security'].ticker} from account" in response.content.decode()
        assert not Holding.objects.filter(
            account=setup["account"], security=setup["security"]
        ).exists()

    def test_bulk_update_shares(self, setup_view):
        """Verify bulk update of multiple holdings."""
        setup = setup_view
        system = setup["system"]

        h1 = Holding.objects.create(account=setup["account"], security=setup["security"], shares=5)
        sec_vxus = system.vxus
        h2 = Holding.objects.create(account=setup["account"], security=sec_vxus, shares=10)

        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {
            f"shares_{setup['security'].ticker}": "7.5",
            f"shares_{sec_vxus.ticker}": "12.0",
        }
        response = setup["client"].post(url, data, follow=True)

        assert "Updated 2 holdings" in response.content.decode()
        h1.refresh_from_db()
        h2.refresh_from_db()
        assert h1.shares == Decimal("7.5")
        assert h2.shares == Decimal("12.0")

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
        assert response.status_code == 404


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
        data = {"security_id": setup["security"].id, "shares": "10.00"}
        response = setup["client"].post(url, data, follow=True)

        assert f"Added 10 shares of {setup['security'].ticker}" in response.content.decode()
        holding = Holding.objects.get(account=setup["account"], security=setup["security"])
        assert holding.shares == Decimal("10.00")

    def test_add_holding_existing_warning(self, setup_view):
        """Verify warning when attempting to add duplicate holding."""
        setup = setup_view
        Holding.objects.create(account=setup["account"], security=setup["security"], shares=5)

        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {"security_id": setup["security"].id, "shares": "10.00"}
        response = setup["client"].post(url, data, follow=True)

        assert f"Holding for {setup['security'].ticker} already exists" in response.content.decode()
        holding = Holding.objects.get(account=setup["account"], security=setup["security"])
        assert holding.shares == Decimal("5.00")

    def test_add_holding_invalid_form(self, setup_view):
        """Verify validation errors for invalid inputs."""
        setup = setup_view
        url = reverse("portfolio:account_holdings", args=[setup["account"].id])

        # Test missing shares
        data = {"security_id": setup["security"].id}
        response = setup["client"].post(url, data, follow=True)
        assert "Shares is required" in response.content.decode()

        # Test non-numeric shares
        data = {"security_id": setup["security"].id, "shares": "abc"}
        response = setup["client"].post(url, data, follow=True)
        assert "must be a valid number" in response.content.decode()

        # Test zero shares
        data = {"security_id": setup["security"].id, "shares": "0"}
        response = setup["client"].post(url, data, follow=True)
        assert "greater than zero" in response.content.decode()

    def test_delete_holding(self, setup_view):
        """Verify successful deletion of a holding using its ID."""
        setup = setup_view
        holding = Holding.objects.create(
            account=setup["account"], security=setup["security"], shares=5
        )

        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {"delete_holding_id": holding.id}
        response = setup["client"].post(url, data, follow=True)

        assert f"Deleted 5 shares of {setup['security'].ticker}" in response.content.decode()
        assert not Holding.objects.filter(id=holding.id).exists()

    def test_bulk_update_shares(self, setup_view):
        """Verify bulk update of multiple holdings using ID-based logic."""
        setup = setup_view
        system = setup["system"]

        h1 = Holding.objects.create(account=setup["account"], security=setup["security"], shares=5)
        sec_vxus = system.vxus
        h2 = Holding.objects.create(account=setup["account"], security=sec_vxus, shares=10)

        url = reverse("portfolio:account_holdings", args=[setup["account"].id])
        data = {
            "holding_ids": [h1.id, h2.id],
            f"shares_{h1.id}": "7.5",
            f"shares_{h2.id}": "12.0",
        }
        response = setup["client"].post(url, data, follow=True)

        assert "Updated 2 holdings" in response.content.decode()
        h1.refresh_from_db()
        h2.refresh_from_db()
        assert h1.shares == Decimal("7.5")
        assert h2.shares == Decimal("12.0")


@pytest.mark.views
@pytest.mark.integration
class TestHoldingsViewSecurity:
    """Integration tests for security validation in holdings view."""

    @pytest.fixture
    def other_user(self, django_user_model):
        """Create a second user."""
        return django_user_model.objects.create_user(
            username="otheruser",
            password="testpass123",  # pragma: allowlist secret
        )

    @pytest.fixture
    def other_user_account(self, other_user, base_system_data):
        """Create account owned by other user."""
        from portfolio.models import Portfolio as PortfolioModel

        portfolio = PortfolioModel.objects.create(user=other_user, name="Other Portfolio")
        return Account.objects.create(
            user=other_user,
            portfolio=portfolio,
            name="Other Account",
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

    def test_cannot_access_other_users_account(self, client, test_user, other_user_account):
        """Test that user cannot access another user's account (redirects with error)."""
        client.force_login(test_user)

        url = reverse("portfolio:account_holdings", args=[other_user_account.id])
        response = client.get(url, follow=True)

        # Should redirect to aggregated holdings views
        assert response.status_code == 200
        messages = list(response.context["messages"])
        assert any("permission" in str(m).lower() for m in messages)

    def test_invalid_account_id_returns_404(self, client, test_user):
        """Test that non-existent account ID returns 404."""
        client.force_login(test_user)

        url = reverse("portfolio:account_holdings", args=[99999])
        response = client.get(url)

        assert response.status_code == 404

    def test_cannot_edit_other_users_holding(
        self, client, test_user, other_user_account, base_system_data
    ):
        """Test that user cannot edit another user's holding via bulk update or direct post."""
        # Create holding for other user
        holding = Holding.objects.create(
            account=other_user_account, security=base_system_data.vti, shares=Decimal("100.00")
        )

        client.force_login(test_user)

        # Attempting to POST to an account the user doesn't own should fail
        url = reverse("portfolio:account_holdings", args=[other_user_account.id])
        response = client.post(url, {"holding_id": holding.id, "shares": "200.00"}, follow=True)

        # Should redirect with error
        assert response.status_code == 200
        messages = list(response.context["messages"])
        assert any("permission" in str(m).lower() for m in messages)

        # Holding should not be modified
        holding.refresh_from_db()
        assert holding.shares == Decimal("100.00")

    def test_invalid_view_mode_uses_default(self, client, test_user):
        """Test that invalid view mode falls back to default safely."""
        client.force_login(test_user)

        url = reverse("portfolio:holdings") + "?view=invalid_mode"
        response = client.get(url)

        assert response.status_code == 200
        # Should use default mode (aggregated)
        assert response.context["is_aggregated"] is True
        messages = list(response.context["messages"])
        assert any("invalid view mode" in str(m).lower() for m in messages)

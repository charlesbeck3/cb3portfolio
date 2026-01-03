"""Tests for rebalancing views."""

from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

import pytest

from portfolio.models import (
    AllocationStrategy,
    Holding,
    SecurityPrice,
    TargetAllocation,
)


@pytest.mark.django_db
class TestRebalancingView:
    """Tests for RebalancingView."""

    @pytest.fixture
    def account_setup(self, test_portfolio, roth_account, client):
        """Set up account with holdings and targets."""
        system = test_portfolio["system"]
        user = test_portfolio["user"]

        # Create holding
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create strategy
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="Test Strategy",
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("60.00"),
        )

        roth_account.allocation_strategy = strategy
        roth_account.save()

        client.force_login(user)

        return {
            "user": user,
            "account": roth_account,
            "strategy": strategy,
            "client": client,
        }

    def test_rebalancing_view_requires_login(self, client, roth_account):
        """Test that unauthenticated users are redirected."""
        url = reverse("portfolio:rebalancing", kwargs={"account_id": roth_account.id})
        response = client.get(url)

        assert response.status_code == 302
        assert "/login/" in response.url

    def test_rebalancing_view_own_account(self, account_setup):
        """Test viewing rebalancing for own account."""
        client = account_setup["client"]
        account = account_setup["account"]

        url = reverse("portfolio:rebalancing", kwargs={"account_id": account.id})
        response = client.get(url)

        assert response.status_code == 200
        assert "plan" in response.context
        assert "account" in response.context
        assert response.context["account"] == account

    def test_rebalancing_view_other_users_account(self, account_setup, django_user_model):
        """Test that users cannot view other users' accounts."""
        client = account_setup["client"]

        # Create another user's account
        other_user = django_user_model.objects.create_user(username="other", password="testpass123")
        from portfolio.models import Account, AccountType, Institution, Portfolio

        portfolio = Portfolio.objects.create(user=other_user, name="Other Portfolio")
        account_type = AccountType.objects.first()
        institution = Institution.objects.first()
        other_account = Account.objects.create(
            portfolio=portfolio,
            account_type=account_type,
            institution=institution,
            name="Other Account",
            user=other_user,
        )

        url = reverse("portfolio:rebalancing", kwargs={"account_id": other_account.id})
        response = client.get(url)

        # Should redirect with error
        assert response.status_code == 302

    def test_rebalancing_view_invalid_account(self, account_setup):
        """Test viewing rebalancing for non-existent account."""
        client = account_setup["client"]

        url = reverse("portfolio:rebalancing", kwargs={"account_id": 99999})
        response = client.get(url)

        # Should redirect with error (validation error redirects to holdings)
        # The view validates account ownership which raises an error and redirects
        assert response.status_code in (302, 404)

    def test_rebalancing_view_template_used(self, account_setup):
        """Test that correct template is used."""
        client = account_setup["client"]
        account = account_setup["account"]

        url = reverse("portfolio:rebalancing", kwargs={"account_id": account.id})
        response = client.get(url)

        assert response.status_code == 200
        assert "portfolio/rebalancing.html" in [t.name for t in response.templates]

    def test_rebalancing_view_context_has_target_allocations(self, account_setup):
        """Test that context includes target allocations."""
        client = account_setup["client"]
        account = account_setup["account"]

        url = reverse("portfolio:rebalancing", kwargs={"account_id": account.id})
        response = client.get(url)

        assert response.status_code == 200
        assert "target_allocations" in response.context
        assert len(response.context["target_allocations"]) > 0


@pytest.mark.django_db
class TestRebalancingExportView:
    """Tests for RebalancingExportView."""

    @pytest.fixture
    def account_setup(self, test_portfolio, roth_account, client):
        """Set up account with holdings and targets."""
        system = test_portfolio["system"]
        user = test_portfolio["user"]

        # Create holding
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create strategy
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="Test Strategy",
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("60.00"),
        )

        roth_account.allocation_strategy = strategy
        roth_account.save()

        client.force_login(user)

        return {
            "user": user,
            "account": roth_account,
            "client": client,
        }

    def test_export_requires_login(self, client, roth_account):
        """Test that export requires authentication."""
        url = reverse("portfolio:rebalancing_export", kwargs={"account_id": roth_account.id})
        response = client.get(url)

        assert response.status_code == 302
        assert "/login/" in response.url

    def test_export_returns_csv(self, account_setup):
        """Test that export returns CSV content type."""
        client = account_setup["client"]
        account = account_setup["account"]

        url = reverse("portfolio:rebalancing_export", kwargs={"account_id": account.id})
        response = client.get(url)

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

    def test_export_has_attachment_header(self, account_setup):
        """Test that export has Content-Disposition header."""
        client = account_setup["client"]
        account = account_setup["account"]

        url = reverse("portfolio:rebalancing_export", kwargs={"account_id": account.id})
        response = client.get(url)

        assert response.status_code == 200
        assert "attachment" in response["Content-Disposition"]
        assert "rebalancing_" in response["Content-Disposition"]
        assert ".csv" in response["Content-Disposition"]

    def test_export_csv_has_header_row(self, account_setup):
        """Test that CSV has proper header row."""
        client = account_setup["client"]
        account = account_setup["account"]

        url = reverse("portfolio:rebalancing_export", kwargs={"account_id": account.id})
        response = client.get(url)

        content = response.content.decode("utf-8")
        lines = content.strip().split("\n")

        assert len(lines) >= 1
        header = lines[0]
        assert "Action" in header
        assert "Ticker" in header
        assert "Shares" in header

    def test_export_other_users_account_denied(self, account_setup, django_user_model):
        """Test that users cannot export other users' accounts."""
        client = account_setup["client"]

        # Create another user's account
        other_user = django_user_model.objects.create_user(username="other", password="testpass123")
        from portfolio.models import Account, AccountType, Institution, Portfolio

        portfolio = Portfolio.objects.create(user=other_user, name="Other Portfolio")
        account_type = AccountType.objects.first()
        institution = Institution.objects.first()
        other_account = Account.objects.create(
            portfolio=portfolio,
            account_type=account_type,
            institution=institution,
            name="Other Account",
            user=other_user,
        )

        url = reverse("portfolio:rebalancing_export", kwargs={"account_id": other_account.id})
        response = client.get(url)

        # Should redirect with error
        assert response.status_code == 302

from decimal import Decimal

from django.utils import timezone

import pytest

from portfolio.models import Account, Holding, SecurityPrice
from portfolio.views.dashboard import DashboardView


@pytest.mark.django_db
@pytest.mark.views
@pytest.mark.integration
class TestPortfolioContextMixin:
    """Test PortfolioContextMixin functionality."""

    def test_get_sidebar_context_unauthenticated(self, rf):
        """Test get_sidebar_context with unauthenticated user."""
        from django.contrib.auth.models import AnonymousUser

        request = rf.get("/")
        request.user = AnonymousUser()

        view = DashboardView()
        view.request = request

        context = view.get_sidebar_context()

        assert "sidebar_data" in context
        assert context["sidebar_data"]["grand_total"] == Decimal("0.00")
        assert context["sidebar_data"]["groups"] == {}

    def test_get_sidebar_context_with_holdings(
        self, rf, test_user, test_portfolio, base_system_data
    ):
        """Test sidebar context calculation with actual holdings."""
        # Setup: Create account with holdings
        account = Account.objects.create(
            user=test_user,
            name="Test Account",
            portfolio=test_portfolio["portfolio"],
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        Holding.objects.create(
            account=account, security=base_system_data.vti, shares=Decimal("10.00")
        )

        # Create price
        now = timezone.now()
        SecurityPrice.objects.create(
            security=base_system_data.vti,
            price=Decimal("100.00"),
            price_datetime=now,
            source="test",
        )

        # Execute
        request = rf.get("/")
        request.user = test_user

        view = DashboardView()
        view.request = request

        context = view.get_sidebar_context()

        # Verify
        assert "sidebar_data" in context
        # Grand total should be 10.00 shares * 100.00 price = 1000.00
        assert context["sidebar_data"]["grand_total"] == Decimal("1000.00")
        assert len(context["sidebar_data"]["groups"]) > 0

        # Verify account appears in correct group
        group_name = base_system_data.type_roth.group.name
        assert group_name in context["sidebar_data"]["groups"]
        group_accounts = context["sidebar_data"]["groups"][group_name]["accounts"]
        assert len(group_accounts) == 1
        assert group_accounts[0]["name"] == "Test Account"
        assert group_accounts[0]["total"] == Decimal("1000.00")

    def test_sidebar_groups_totals(self, rf, test_user, test_portfolio, base_system_data):
        """Test that group totals aggregate correctly."""
        # Create two accounts in same group
        account1 = Account.objects.create(
            user=test_user,
            name="Roth 1",
            portfolio=test_portfolio["portfolio"],
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )
        account2 = Account.objects.create(
            user=test_user,
            name="Roth 2",
            portfolio=test_portfolio["portfolio"],
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        # Add holdings
        Holding.objects.create(
            account=account1, security=base_system_data.vti, shares=Decimal("10.00")
        )
        Holding.objects.create(
            account=account2, security=base_system_data.vti, shares=Decimal("5.00")
        )

        # Create price
        now = timezone.now()
        SecurityPrice.objects.create(
            security=base_system_data.vti,
            price=Decimal("100.00"),
            price_datetime=now,
            source="test",
        )

        # Execute
        request = rf.get("/")
        request.user = test_user

        view = DashboardView()
        view.request = request

        context = view.get_sidebar_context()

        # Group total should be sum of both accounts (1000 + 500 = 1500)
        group_name = base_system_data.type_roth.group.name
        assert context["sidebar_data"]["groups"][group_name]["total"] == Decimal("1500.00")

    def test_sidebar_includes_variances(self, rf, test_user, test_portfolio, base_system_data):
        """Test that sidebar includes drift/variance data for accounts."""
        account = Account.objects.create(
            user=test_user,
            name="Test Account",
            portfolio=test_portfolio["portfolio"],
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        Holding.objects.create(
            account=account, security=base_system_data.vti, shares=Decimal("10.00")
        )

        now = timezone.now()
        SecurityPrice.objects.create(
            security=base_system_data.vti,
            price=Decimal("100.00"),
            price_datetime=now,
            source="test",
        )

        request = rf.get("/")
        request.user = test_user

        view = DashboardView()
        view.request = request

        context = view.get_sidebar_context()

        # Verify variance data is present
        group_name = base_system_data.type_roth.group.name
        account_data = context["sidebar_data"]["groups"][group_name]["accounts"][0]
        assert "absolute_deviation_pct" in account_data
        # Variance should be a Decimal
        assert isinstance(account_data["absolute_deviation_pct"], Decimal)

    def test_sidebar_price_update_failure_handling(
        self, rf, test_user, test_portfolio, base_system_data, monkeypatch
    ):
        """Test that sidebar handles price update failures gracefully."""

        # Mock pricing service to raise exception
        def mock_update_raises(*args, **kwargs):
            raise Exception("Price fetch failed")

        monkeypatch.setattr(
            "portfolio.services.pricing.PricingService.update_holdings_prices",
            mock_update_raises,
        )

        request = rf.get("/")
        request.user = test_user

        view = DashboardView()
        view.request = request

        # Should not raise - should log and continue
        context = view.get_sidebar_context()
        assert "sidebar_data" in context

    def test_empty_portfolio_sidebar(self, rf, test_user):
        """Test sidebar with no accounts."""
        request = rf.get("/")
        request.user = test_user

        view = DashboardView()
        view.request = request

        context = view.get_sidebar_context()

        assert context["sidebar_data"]["grand_total"] == Decimal("0.00")
        assert context["sidebar_data"]["groups"] == {}

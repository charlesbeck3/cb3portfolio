"""
Tests for allocation strategy views.

Tests: portfolio/views/strategies.py
- AllocationStrategyCreateView
- AllocationStrategyUpdateView
"""

from decimal import Decimal

from django.urls import reverse

import pytest

from portfolio.exceptions import AllocationError
from portfolio.models import AllocationStrategy


@pytest.mark.views
@pytest.mark.integration
class TestAllocationStrategyViews:
    """Tests for creating and updating allocation strategies."""

    @pytest.fixture
    def setup_view(self, client, test_user, base_system_data):
        system = base_system_data
        client.force_login(test_user)

        return {
            "client": client,
            "user": test_user,
            "system": system,
            "ac1": system.asset_class_us_equities,
            "ac2": system.asset_class_intl_developed,
            "cash": system.asset_class_cash,
        }

    def test_create_strategy_with_cash_remainder(self, setup_view):
        """Verify cash is calculated as remainder."""
        setup = setup_view
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Test Strategy",
            f"target_{setup['ac1'].id}": "60.00",
            f"target_{setup['ac2'].id}": "30.00",
        }

        response = setup["client"].post(url, data)
        assert response.status_code == 302
        assert response.url == reverse("portfolio:target_allocations")

        strategy = AllocationStrategy.objects.get(name="Test Strategy")
        assert strategy.target_allocations.get(asset_class=setup["ac1"]).target_percent == Decimal(
            "60.00"
        )
        assert strategy.target_allocations.get(asset_class=setup["ac2"]).target_percent == Decimal(
            "30.00"
        )
        assert strategy.cash_allocation == Decimal("10.00")

    def test_create_strategy_100_percent_no_cash(self, setup_view):
        """Verify 100% allocation results in 0% cash."""
        setup = setup_view
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "No Cash Strategy",
            f"target_{setup['ac1'].id}": "100.00",
        }

        response = setup["client"].post(url, data)
        assert response.status_code == 302

        strategy = AllocationStrategy.objects.get(name="No Cash Strategy")
        assert not strategy.target_allocations.filter(asset_class=setup["cash"]).exists()
        assert strategy.cash_allocation == Decimal("0.00")

    def test_create_strategy_exceeds_100_error(self, setup_view):
        """Verify validation error if > 100%."""
        setup = setup_view
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Invalid Strategy",
            f"target_{setup['ac1'].id}": "60.00",
            f"target_{setup['ac2'].id}": "50.00",
        }

        response = setup["client"].post(url, data)
        assert response.status_code == 200
        assert "Total allocation" in response.content.decode()

    def test_update_strategy_recalculates_cash(self, setup_view):
        """Verify updating strategy recalculates cash correctly."""
        setup = setup_view
        strategy = AllocationStrategy.objects.create(
            user=setup["user"], name="Update Test Strategy"
        )
        strategy.save_allocations(
            {setup["ac1"].id: Decimal("60.00"), setup["ac2"].id: Decimal("30.00")}
        )

        url = reverse("portfolio:strategy_update", args=[strategy.id])
        data = {
            "name": "Update Test Strategy",
            f"target_{setup['ac1'].id}": "50.00",
            f"target_{setup['ac2'].id}": "20.00",
        }

        response = setup["client"].post(url, data)
        assert response.status_code == 302

        strategy.refresh_from_db()
        assert strategy.target_allocations.get(asset_class=setup["ac1"]).target_percent == Decimal(
            "50.00"
        )
        assert strategy.cash_allocation == Decimal("30.00")

    def test_create_strategy_with_explicit_cash(self, setup_view):
        """Verify user can explicitly provide cash allocation."""
        setup = setup_view
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Explicit Cash Strategy",
            f"target_{setup['ac1'].id}": "60.00",
            f"target_{setup['ac2'].id}": "30.00",
            f"target_{setup['cash'].id}": "10.00",
        }

        response = setup["client"].post(url, data)
        assert response.status_code == 302

        strategy = AllocationStrategy.objects.get(name="Explicit Cash Strategy")
        assert strategy.cash_allocation == Decimal("10.00")

    def test_save_allocations_direct_with_explicit_cash(self, setup_view):
        """Test save_allocations() domain method with explicit cash."""
        setup = setup_view
        strategy = AllocationStrategy.objects.create(user=setup["user"], name="Direct Test")
        strategy.save_allocations(
            {
                setup["ac1"].id: Decimal("60.00"),
                setup["ac2"].id: Decimal("30.00"),
                setup["cash"].id: Decimal("10.00"),
            }
        )

        assert strategy.cash_allocation == Decimal("10.00")
        total = sum(ta.target_percent for ta in strategy.target_allocations.all())
        assert total == Decimal("100.00")

    def test_save_allocations_direct_explicit_cash_wrong_sum(self, setup_view):
        """Test save_allocations() domain method errors on wrong sum with explicit cash."""
        setup = setup_view
        strategy = AllocationStrategy.objects.create(user=setup["user"], name="Direct Test")

        with pytest.raises(AllocationError) as excinfo:
            strategy.save_allocations(
                {
                    setup["ac1"].id: Decimal("60.00"),
                    setup["ac2"].id: Decimal("30.00"),
                    setup["cash"].id: Decimal("15.00"),
                }
            )
        assert "105" in str(excinfo.value)
        assert "100" in str(excinfo.value)

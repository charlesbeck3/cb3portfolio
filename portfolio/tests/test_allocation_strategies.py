from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest

from portfolio.models import AllocationStrategy

User = get_user_model()


@pytest.fixture
def strategy(test_user: Any) -> AllocationStrategy:
    return AllocationStrategy.objects.create(user=test_user, name="Test Strategy")


@pytest.mark.models
@pytest.mark.integration
class TestAllocationStrategyCashCalculation:
    """Test the extracted cash allocation calculation logic."""

    def test_calculate_cash_allocation_simple_remainder(self, strategy: AllocationStrategy) -> None:
        """Test cash calculation with simple 60/30 split."""
        allocations = {
            1: Decimal("60.00"),
            2: Decimal("30.00"),
        }
        cash = strategy.calculate_cash_allocation(allocations)
        assert cash == Decimal("10.00")

    def test_calculate_cash_allocation_zero_remainder(self, strategy: AllocationStrategy) -> None:
        """Test cash calculation when allocations sum to 100%."""
        allocations = {
            1: Decimal("100.00"),
        }
        cash = strategy.calculate_cash_allocation(allocations)
        assert cash == Decimal("0.00")

    def test_calculate_cash_allocation_small_remainder(self, strategy: AllocationStrategy) -> None:
        """Test cash calculation with small remainder."""
        allocations = {
            1: Decimal("99.50"),
        }
        cash = strategy.calculate_cash_allocation(allocations)
        assert cash == Decimal("0.50")

    def test_calculate_cash_allocation_multiple_assets(self, strategy: AllocationStrategy) -> None:
        """Test cash calculation with multiple asset classes."""
        allocations = {
            1: Decimal("40.00"),
            2: Decimal("25.00"),
            3: Decimal("20.00"),
        }
        cash = strategy.calculate_cash_allocation(allocations)
        assert cash == Decimal("15.00")

    def test_calculate_cash_allocation_empty_dict(self, strategy: AllocationStrategy) -> None:
        """Test cash calculation with no allocations (100% cash)."""
        allocations: dict[int, Decimal] = {}
        cash = strategy.calculate_cash_allocation(allocations)
        assert cash == Decimal("100.00")


@pytest.mark.models
@pytest.mark.integration
class TestAllocationStrategyValidation:
    """Test defensive validation in AllocationStrategy.save_allocations()."""

    def test_save_allocations_validates_total(
        self, strategy: AllocationStrategy, base_system_data: Any
    ) -> None:
        """Verify save_allocations() catches total != 100%."""
        system = base_system_data

        # This should work (implicit cash)
        strategy.save_allocations(
            {
                system.asset_class_us_equities.id: Decimal("60.00"),
                system.asset_class_intl_developed.id: Decimal("40.00"),
            }
        )

        # Verify saved correctly
        total = sum(ta.target_percent for ta in strategy.target_allocations.all())
        assert total == Decimal("100.00")

    def test_save_allocations_prevents_invalid_data(
        self, strategy: AllocationStrategy, base_system_data: Any
    ) -> None:
        """Verify save_allocations() fails fast on calculation errors."""
        system = base_system_data

        # Manually create invalid allocations that don't sum to 100%
        invalid_allocations = {
            system.asset_class_us_equities.id: Decimal("60.00"),
            system.asset_class_intl_developed.id: Decimal("30.00"),
            system.asset_class_cash.id: Decimal("5.00"),  # Sums to 95%
        }

        with pytest.raises(ValueError, match="expected exactly 100.00%"):
            strategy.save_allocations(invalid_allocations)

    def test_validate_allocations_helper(
        self, strategy: AllocationStrategy, base_system_data: Any
    ) -> None:
        """Test validate_allocations() helper method."""
        system = base_system_data

        # Valid allocations
        valid = {
            system.asset_class_us_equities.id: Decimal("60.00"),
            system.asset_class_intl_developed.id: Decimal("30.00"),
            system.asset_class_cash.id: Decimal("10.00"),
        }
        is_valid, error = strategy.validate_allocations(valid)
        assert is_valid
        assert error == ""

        # Invalid - sum to 95%
        invalid = {
            system.asset_class_us_equities.id: Decimal("60.00"),
            system.asset_class_intl_developed.id: Decimal("30.00"),
            system.asset_class_cash.id: Decimal("5.00"),
        }
        is_valid, error = strategy.validate_allocations(invalid)
        assert not is_valid
        assert "95" in error
        assert "100" in error

        # Invalid - sum to 105%
        over = {
            system.asset_class_us_equities.id: Decimal("60.00"),
            system.asset_class_intl_developed.id: Decimal("30.00"),
            system.asset_class_cash.id: Decimal("15.00"),
        }
        is_valid, error = strategy.validate_allocations(over)
        assert not is_valid
        assert "105" in error

    def test_rounding_within_tolerance(
        self, strategy: AllocationStrategy, base_system_data: Any
    ) -> None:
        """Verify tiny rounding errors are accepted."""
        system = base_system_data

        # Allocations with tiny rounding error (100.0001%)
        nearly_100 = {
            system.asset_class_us_equities.id: Decimal("33.3333"),
            system.asset_class_intl_developed.id: Decimal("33.3333"),
            system.asset_class_cash.id: Decimal("33.3334"),
        }

        # Should not raise (within 0.001% tolerance)
        try:
            strategy.save_allocations(nearly_100)
        except ValueError:
            pytest.fail("Should accept allocations within tolerance")

        # Verify they sum to 100.00 exactly in DB (or close to it)
        total = sum(ta.target_percent for ta in strategy.target_allocations.all())
        assert abs(total - Decimal("100.00")) <= Decimal("0.02")

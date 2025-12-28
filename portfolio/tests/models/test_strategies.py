from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

import pytest

from portfolio.exceptions import AllocationError
from portfolio.models import AllocationStrategy, AssetClass, TargetAllocation

User = get_user_model()


@pytest.fixture
def strategy(test_user: Any) -> AllocationStrategy:
    """Fixture for a clean allocation strategy."""
    return AllocationStrategy.objects.create(user=test_user, name="Test Strategy")


@pytest.mark.models
@pytest.mark.integration
class TestTargetAllocation:
    def test_create_target_allocation(self, test_user: Any, base_system_data: Any) -> None:
        """Test creating a target allocation."""
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        asset_class = AssetClass.objects.create(
            name="US Stocks TA",
            category=system.cat_us_eq,
        )

        target = TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=asset_class,
            target_percent=Decimal("40.00"),
        )
        assert target.target_percent == Decimal("40.00")
        assert str(target) == f"{strategy.name}: {asset_class.name} - 40.00%"

    def test_target_allocation_isolation(self, test_user: Any, base_system_data: Any) -> None:
        """Test that different users can have their own allocations."""
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy 1")
        asset_class = AssetClass.objects.create(
            name="US Stocks Iso",
            category=system.cat_us_eq,
        )

        # User 1 allocation
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=asset_class,
            target_percent=Decimal("40.00"),
        )

        # User 2 allocation
        user2 = User.objects.create_user(username="otheruser", password="password")
        strategy2 = AllocationStrategy.objects.create(user=user2, name="Test Strategy 2")
        target2 = TargetAllocation.objects.create(
            strategy=strategy2,
            asset_class=asset_class,
            target_percent=Decimal("60.00"),
        )

        # Count total
        assert TargetAllocation.objects.filter(asset_class=asset_class).count() == 2
        assert target2.strategy.user.username == "otheruser"
        assert target2.target_percent == Decimal("60.00")

    def test_target_value_for(self, test_user: Any, base_system_data: Any) -> None:
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        asset_class = AssetClass.objects.create(name="US Stocks ValFor", category=system.cat_us_eq)

        allocation = TargetAllocation(
            strategy=strategy,
            asset_class=asset_class,
            target_percent=Decimal("25"),
        )
        assert allocation.target_value_for(Decimal("10000")) == Decimal("2500")

    def test_validate_allocation_set_valid(self, test_user: Any, base_system_data: Any) -> None:
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        ac1 = AssetClass.objects.create(name="AC1", category=system.cat_us_eq)
        ac2 = AssetClass.objects.create(name="AC2", category=system.cat_us_eq)

        allocations = [
            TargetAllocation(
                strategy=strategy,
                asset_class=ac1,
                target_percent=Decimal("60"),
            ),
            TargetAllocation(
                strategy=strategy,
                asset_class=ac2,
                target_percent=Decimal("40"),
            ),
        ]
        ok, msg = TargetAllocation.validate_allocation_set(allocations)
        assert ok
        assert msg == ""

    def test_validate_allocation_set_exceeds_100(
        self, test_user: Any, base_system_data: Any
    ) -> None:
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        ac1 = AssetClass.objects.create(name="AC1", category=system.cat_us_eq)

        allocations = [
            TargetAllocation(
                strategy=strategy,
                asset_class=ac1,
                target_percent=Decimal("60"),
            ),
            TargetAllocation(
                strategy=strategy,
                asset_class=ac1,  # Same or diff doesn't matter for this test logic usually, but let's assume same strategy list
                target_percent=Decimal("50"),
            ),
        ]
        ok, msg = TargetAllocation.validate_allocation_set(allocations)
        assert not ok
        assert "110" in msg


@pytest.mark.models
@pytest.mark.integration
def test_target_allocation_negative_validation(test_user: Any, base_system_data: Any) -> None:
    """Test that negative allocations are rejected."""
    system = base_system_data
    strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
    asset_class, _ = AssetClass.objects.get_or_create(
        name="US Equities", defaults={"category": system.cat_us_eq}
    )

    allocation = TargetAllocation(
        strategy=strategy,
        asset_class=asset_class,
        target_percent=Decimal("-10.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        allocation.full_clean()

    assert "target_percent" in exc_info.value.message_dict
    assert "negative" in str(exc_info.value).lower()


@pytest.mark.models
@pytest.mark.integration
def test_target_allocation_over_100_validation(test_user: Any, base_system_data: Any) -> None:
    """Test that allocations over 100% are rejected."""
    system = base_system_data
    strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
    asset_class, _ = AssetClass.objects.get_or_create(
        name="US Equities", defaults={"category": system.cat_us_eq}
    )

    allocation = TargetAllocation(
        strategy=strategy,
        asset_class=asset_class,
        target_percent=Decimal("150.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        allocation.full_clean()

    assert "target_percent" in exc_info.value.message_dict
    assert "100" in str(exc_info.value)


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

        with pytest.raises(AllocationError, match="expected exactly 100.00%"):
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

    def test_rounding_within_tolerance(
        self, strategy: AllocationStrategy, base_system_data: Any
    ) -> None:
        """Verify tiny rounding errors are accepted.

        Migrated from: test_allocation_strategies_legacy.py::test_rounding_within_tolerance
        """
        system = base_system_data

        # Allocations with tiny rounding error (100.0001%)
        nearly_100 = {
            system.asset_class_us_equities.id: Decimal("33.3333"),
            system.asset_class_intl_developed.id: Decimal("33.3333"),
            system.asset_class_cash.id: Decimal("33.3334"),
        }

        # Should not raise (within 0.02% tolerance based on assert below)
        strategy.save_allocations(nearly_100)

        # Verify they sum to 100.00 exactly in DB (or close to it)
        total = sum(ta.target_percent for ta in strategy.target_allocations.all())
        assert abs(total - Decimal("100.00")) <= Decimal("0.02")

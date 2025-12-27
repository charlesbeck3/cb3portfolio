from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

import pytest

from portfolio.models import AllocationStrategy, AssetClass, TargetAllocation

User = get_user_model()


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

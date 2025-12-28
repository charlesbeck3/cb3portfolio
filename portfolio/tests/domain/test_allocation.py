"""
Tests for asset allocation domain value object.

Tests: portfolio/domain/allocation.py
"""

from decimal import Decimal

import pytest

from portfolio.domain import AssetAllocation


@pytest.mark.domain
@pytest.mark.unit
class TestAssetAllocation:
    """Tests for the AssetAllocation value object."""

    def test_target_value_for(self) -> None:
        """Verify target dollar calculation."""
        allocation = AssetAllocation(asset_class_name="US Equities", target_pct=Decimal("25"))
        target = allocation.target_value_for(Decimal("10000"))
        assert target == Decimal("2500")

    def test_variance_for(self) -> None:
        """Verify dollar variance calculation."""
        allocation = AssetAllocation(asset_class_name="US Equities", target_pct=Decimal("25"))
        # Current: $3000, Target: 25% of $10000 = $2500 -> variance: +$500
        variance = allocation.variance_for(Decimal("3000"), Decimal("10000"))
        assert variance == Decimal("500")

    def test_variance_pct_for_handles_zero_total(self) -> None:
        """Verify zero total value doesn't cause division by zero."""
        allocation = AssetAllocation(asset_class_name="US Equities", target_pct=Decimal("25"))
        variance_pct = allocation.variance_pct_for(Decimal("0"), Decimal("0"))
        assert variance_pct == Decimal("0.00")

from decimal import Decimal

from django.test import TestCase

from portfolio.domain import AssetAllocation


class AssetAllocationTests(TestCase):
    def test_target_value_for(self) -> None:
        allocation = AssetAllocation(asset_class_name="US Stocks", target_pct=Decimal("25"))
        target = allocation.target_value_for(Decimal("10000"))
        self.assertEqual(target, Decimal("2500"))

    def test_variance_for(self) -> None:
        allocation = AssetAllocation(asset_class_name="US Stocks", target_pct=Decimal("25"))
        # Current: $3000, Target: 25% of $10000 = $2500 -> variance: +$500
        variance = allocation.variance_for(Decimal("3000"), Decimal("10000"))
        self.assertEqual(variance, Decimal("500"))

    def test_variance_pct_for_handles_zero_total(self) -> None:
        allocation = AssetAllocation(asset_class_name="US Stocks", target_pct=Decimal("25"))
        variance_pct = allocation.variance_pct_for(Decimal("0"), Decimal("0"))
        self.assertEqual(variance_pct, Decimal("0.00"))

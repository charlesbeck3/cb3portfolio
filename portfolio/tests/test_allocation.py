from decimal import Decimal

from django.test import TestCase

from portfolio.domain import AssetAllocation


class AssetAllocationTests(TestCase):
    def test_apply_to_total(self) -> None:
        allocation = AssetAllocation(weights={"Stocks": Decimal("60"), "Bonds": Decimal("40")})
        result = allocation.apply_to(Decimal("10000"))

        self.assertEqual(result["Stocks"], Decimal("6000"))
        self.assertEqual(result["Bonds"], Decimal("4000"))

    def test_total_pct(self) -> None:
        allocation = AssetAllocation(weights={"Stocks": Decimal("70"), "Bonds": Decimal("20")})
        self.assertEqual(allocation.total_pct(), Decimal("90"))

    def test_variance_from_other(self) -> None:
        base = AssetAllocation(weights={"Stocks": Decimal("60"), "Bonds": Decimal("40")})
        other = AssetAllocation(weights={"Stocks": Decimal("50")})

        variance = base.variance_from(other)

        self.assertEqual(variance.weights["Stocks"], Decimal("10"))
        self.assertEqual(variance.weights["Bonds"], Decimal("40"))

    def test_merge_with_other(self) -> None:
        base = AssetAllocation(weights={"Stocks": Decimal("60"), "Bonds": Decimal("40")})
        overrides = AssetAllocation(weights={"Stocks": Decimal("50"), "RealEstate": Decimal("10")})

        merged = base.merge_with(overrides)

        self.assertEqual(merged.weights["Stocks"], Decimal("50"))
        self.assertEqual(merged.weights["Bonds"], Decimal("40"))
        self.assertEqual(merged.weights["RealEstate"], Decimal("10"))

    def test_apply_to_negative_total_raises(self) -> None:
        allocation = AssetAllocation(weights={"Stocks": Decimal("60")})

        with self.assertRaises(ValueError):
            allocation.apply_to(Decimal("-1"))

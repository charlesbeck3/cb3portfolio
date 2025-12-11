from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class AssetAllocation:
    """Immutable allocation specification by asset class name.

    Percentages are stored on a 0-100 scale using ``Decimal``.
    Keys are arbitrary asset class identifiers (typically names or codes).
    """

    weights: Mapping[str, Decimal] = field(default_factory=dict)

    def apply_to(self, total: Decimal) -> dict[str, Decimal]:
        """Apply this allocation to a total value.

        Returns a mapping of key -> dollar amount such that each value is
        ``total * pct / 100``.
        """

        if total < 0:
            raise ValueError("total must be non-negative")

        result: dict[str, Decimal] = {}
        for key, pct in self.weights.items():
            result[key] = (total * pct) / Decimal("100")
        return result

    def variance_from(self, other: AssetAllocation) -> AssetAllocation:
        """Return allocation representing ``self - other`` per key.

        Missing keys are treated as 0 in both allocations.
        """

        all_keys = set(self.weights.keys()) | set(other.weights.keys())
        diff: dict[str, Decimal] = {}

        for key in all_keys:
            a = self.weights.get(key, Decimal("0"))
            b = other.weights.get(key, Decimal("0"))
            diff[key] = a - b

        return AssetAllocation(weights=diff)

    def merge_with(self, other: AssetAllocation) -> AssetAllocation:
        """Merge two allocations, with ``other`` taking precedence on conflicts.

        Keys present only in one allocation are carried through unchanged.
        """

        merged: dict[str, Decimal] = dict(self.weights)
        merged.update(other.weights)
        return AssetAllocation(weights=merged)

    def total_pct(self) -> Decimal:
        """Return the sum of all allocation percentages.

        This does *not* enforce that the total is exactly 100%; callers can
        decide whether to treat <100 as leaving room for cash.
        """

        return sum(self.weights.values(), Decimal("0"))

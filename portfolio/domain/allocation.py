from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AssetAllocation:
    """Value object representing an allocation to a single asset class.

    Percentages are expressed on a 0-100 scale (not 0-1).
    """

    asset_class_name: str
    target_pct: Decimal

    def target_value_for(self, account_total: Decimal) -> Decimal:
        """Return the target dollar amount for a given account total."""

        return account_total * self.target_pct / Decimal("100")

    def variance_for(self, current_value: Decimal, account_total: Decimal) -> Decimal:
        """Return dollar variance between current and target values."""

        target_value = self.target_value_for(account_total)
        return current_value - target_value

    def variance_pct_for(self, current_value: Decimal, account_total: Decimal) -> Decimal:
        """Return variance as a percentage of account total.

        When account_total is zero, returns 0 to avoid division by zero.
        """

        if account_total == 0:
            return Decimal("0.00")
        target_value = self.target_value_for(account_total)
        return (current_value - target_value) / account_total * Decimal("100")

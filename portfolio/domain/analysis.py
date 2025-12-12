from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from portfolio.domain.portfolio import Portfolio


@dataclass(frozen=True)
class PortfolioAnalysis:
    """Domain object for analyzing a Portfolio against target allocations."""

    portfolio: Portfolio
    targets: dict[str, Decimal]

    @property
    def total_value(self) -> Decimal:
        return self.portfolio.total_value

    def current_value_by_asset_class(self) -> dict[str, Decimal]:
        return self.portfolio.value_by_asset_class()

    def target_value_for(self, asset_class_name: str) -> Decimal:
        pct = self.targets.get(asset_class_name, Decimal("0.00"))
        return self.total_value * pct / Decimal("100")

    def variance_for(self, asset_class_name: str) -> Decimal:
        current = self.current_value_by_asset_class().get(asset_class_name, Decimal("0.00"))
        target = self.target_value_for(asset_class_name)
        return current - target

    def variance_pct_for(self, asset_class_name: str) -> Decimal:
        if self.total_value == 0:
            return Decimal("0.00")
        return self.variance_for(asset_class_name) / self.total_value * Decimal("100")

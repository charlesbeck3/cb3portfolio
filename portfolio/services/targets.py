from __future__ import annotations

from decimal import Decimal

from portfolio.models import Account, AllocationStrategy
from users.models import CustomUser


class TargetAllocationService:
    """Service for computing effective target allocations per account.

    For now this simply hosts the existing "effective targets" logic that was
    previously on PortfolioSummaryService.get_effective_targets, without
    changing behavior.
    """

    @staticmethod
    def get_effective_targets(user: CustomUser) -> dict[int, dict[str, Decimal]]:
        """Return mapping ``{account_id: {asset_class_name: target_pct}}``.

        Strategy:
        - Resolve effective AllocationStrategy per account.
        - Return that strategy's TargetAllocation rows as an asset-class-name keyed dict.
        - If no strategy is found for an account, return an empty dict for it.
        """

        accounts = Account.objects.filter(user=user).select_related(
            "account_type",
            "portfolio",
            "allocation_strategy",
            "portfolio__allocation_strategy",
        )

        effective_targets: dict[int, dict[str, Decimal]] = {}

        for account in accounts:
            strategy: AllocationStrategy | None = account.get_effective_allocation_strategy()
            if strategy is None:
                effective_targets[account.id] = {}
                continue

            allocations = strategy.target_allocations.select_related("asset_class").all()
            effective_targets[account.id] = {
                a.asset_class.name: a.target_percent
                for a in allocations
            }

        return effective_targets

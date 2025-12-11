from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from portfolio.models import Account, TargetAllocation


class TargetAllocationService:
    """Service for computing effective target allocations per account.

    For now this simply hosts the existing "effective targets" logic that was
    previously on PortfolioSummaryService.get_effective_targets, without
    changing behavior.
    """

    @staticmethod
    def get_effective_targets(user: Any) -> dict[int, dict[str, Decimal]]:
        """Return mapping ``{account_id: {asset_class_name: target_pct}}``.

        Strategy:
        - Build account-type default targets.
        - Overlay account-specific overrides.
        - If any overrides exist for an account, ignore type defaults for it.
        """

        targets = TargetAllocation.objects.filter(user=user).select_related(
            "account_type", "asset_class", "account"
        )

        type_defaults: dict[int, dict[str, Decimal]] = defaultdict(dict)
        account_overrides: dict[int, dict[str, Decimal]] = defaultdict(dict)

        for t in targets:
            ac_name = t.asset_class.name
            if t.account_id:
                account_overrides[t.account_id][ac_name] = t.target_pct
            else:
                type_defaults[t.account_type_id][ac_name] = t.target_pct

        accounts = Account.objects.filter(user=user).select_related("account_type")

        effective_targets: dict[int, dict[str, Decimal]] = {}

        for account in accounts:
            overrides = account_overrides.get(account.id, {})

            if overrides:
                effective_targets[account.id] = overrides.copy()
            else:
                defaults = type_defaults.get(account.account_type_id, {}).copy()
                effective_targets[account.id] = defaults

        return effective_targets

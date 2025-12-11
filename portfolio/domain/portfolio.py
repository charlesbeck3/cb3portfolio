from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from portfolio.models import Account


@dataclass
class Portfolio:
    """Aggregate root representing a user's complete portfolio.

    Encapsulates all accounts and provides portfolio-level calculations.
    """

    user_id: int
    accounts: list[Account] = field(default_factory=list)

    def __iter__(self) -> Iterator[Account]:
        return iter(self.accounts)

    def __len__(self) -> int:
        return len(self.accounts)

    @property
    def total_value(self) -> Decimal:
        """Total market value across all accounts."""

        return sum((account.total_value() for account in self.accounts), Decimal("0.00"))

    def value_by_account_type(self) -> dict[str, Decimal]:
        """Aggregate values by account type code."""

        result: dict[str, Decimal] = {}
        for account in self.accounts:
            code = account.account_type.code
            result[code] = result.get(code, Decimal("0.00")) + account.total_value()
        return result

    def value_by_asset_class(self) -> dict[str, Decimal]:
        """Aggregate values by asset class name across all accounts."""

        result: dict[str, Decimal] = {}
        for account in self.accounts:
            for ac_name, value in account.holdings_by_asset_class().items():
                result[ac_name] = result.get(ac_name, Decimal("0.00")) + value
        return result

    def allocation_by_asset_class(self) -> dict[str, Decimal]:
        """Current allocation percentages by asset class.

        Percentages are on a 0-100 scale. Returns an empty dict when
        portfolio total is zero.
        """

        total = self.total_value
        if total == 0:
            return {}

        by_ac = self.value_by_asset_class()
        return {name: (value / total) * Decimal("100") for name, value in by_ac.items()}

    def variance_from_targets(
        self,
        effective_targets: dict[int, dict[str, Decimal]],
    ) -> dict[str, Decimal]:
        """Return variance (current - target) by asset class across portfolio.

        ``effective_targets`` maps account_id to ``{asset_class_name: target_pct}``.
        """

        # Target dollars per asset class
        target_by_ac: dict[str, Decimal] = {}
        for account in self.accounts:
            account_total = account.total_value()
            account_targets = effective_targets.get(account.id or 0, {})

            for ac_name, target_pct in account_targets.items():
                target_dollars = (account_total * target_pct) / Decimal("100")
                target_by_ac[ac_name] = target_by_ac.get(ac_name, Decimal("0.00")) + target_dollars

        current_by_ac = self.value_by_asset_class()
        all_asset_classes = set(current_by_ac.keys()) | set(target_by_ac.keys())

        return {
            ac_name: current_by_ac.get(ac_name, Decimal("0.00"))
            - target_by_ac.get(ac_name, Decimal("0.00"))
            for ac_name in all_asset_classes
        }

    def account_by_id(self, account_id: int) -> Account | None:
        """Find an account by its primary key, or return None."""

        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def accounts_by_type(self, account_type_code: str) -> list[Account]:
        """Return all accounts with the given account type code."""

        return [acc for acc in self.accounts if acc.account_type.code == account_type_code]

    @classmethod
    def load_for_user(cls, user: Any) -> Portfolio:
        """Factory method to load a complete portfolio for a user.

        Uses Account.objects.get_summary_data to leverage existing manager
        optimisations (select_related/prefetch, etc.).
        """

        from portfolio.models import Account

        accounts = list(Account.objects.get_summary_data(user))
        return cls(user_id=user.id, accounts=accounts)

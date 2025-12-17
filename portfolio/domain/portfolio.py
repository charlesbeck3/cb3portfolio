from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from portfolio.domain.allocation import AssetAllocation

if TYPE_CHECKING:
    from portfolio.models import Account
    from users.models import CustomUser


@dataclass
class Portfolio:
    """Aggregate root representing a user's complete portfolio."""

    user_id: int
    accounts: list[Account] = field(default_factory=list)

    def __iter__(self) -> Iterator[Account]:
        return iter(self.accounts)

    def __len__(self) -> int:
        return len(self.accounts)

    @property
    def total_value(self) -> Decimal:
        """Total value across all accounts."""

        return sum((acc.total_value() for acc in self.accounts), Decimal("0.00"))

    def value_by_account_type(self) -> dict[str, Decimal]:
        """Aggregate values by account type code."""

        result: dict[str, Decimal] = {}
        for account in self.accounts:
            code = account.account_type.code
            result[code] = result.get(code, Decimal("0.00")) + account.total_value()
        return result

    def value_by_asset_class(self) -> dict[str, Decimal]:
        """Aggregate values by asset class across all accounts."""

        result: dict[str, Decimal] = {}
        for account in self.accounts:
            for ac_name, value in account.holdings_by_asset_class().items():
                result[ac_name] = result.get(ac_name, Decimal("0.00")) + value
        return result

    def allocation_by_asset_class(self) -> dict[str, Decimal]:
        """Current allocation percentages by asset class."""

        total = self.total_value
        if total == 0:
            return {}

        by_ac = self.value_by_asset_class()
        return {ac_name: value / total * Decimal("100") for ac_name, value in by_ac.items()}

    def account_by_id(self, account_id: int) -> Account | None:
        """Find an account by ID."""

        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def accounts_by_type(self, account_type_code: str) -> list[Account]:
        """Get all accounts of a specific type."""

        return [acc for acc in self.accounts if acc.account_type.code == account_type_code]

    def get_account_totals(self) -> dict[int, Decimal]:
        """Get total value for each account by account ID."""

        return {acc.id: acc.total_value() for acc in self.accounts}

    def get_account_type_map(self) -> dict[int, str]:
        """Get mapping of account ID to account type code."""

        return {acc.id: acc.account_type.code for acc in self.accounts}

    def variance_from_allocations(
        self,
        effective_allocations: dict[int, list[AssetAllocation]],
    ) -> dict[str, Decimal]:
        """Calculate variance (current - target) by asset class across portfolio.

        Uses AssetAllocation domain objects for calculations.

        Args:
            effective_allocations: {account_id: [AssetAllocation, ...]}

        Returns:
            {asset_class_name: variance_in_dollars}
        """

        target_by_ac: dict[str, Decimal] = {}

        for account in self.accounts:
            account_total = account.total_value()
            allocations = effective_allocations.get(account.id, [])

            for alloc in allocations:
                target_dollars = alloc.target_value_for(account_total)
                target_by_ac[alloc.asset_class_name] = (
                    target_by_ac.get(alloc.asset_class_name, Decimal("0.00")) + target_dollars
                )

        current_by_ac = self.value_by_asset_class()
        all_asset_classes = set(current_by_ac.keys()) | set(target_by_ac.keys())

        return {
            ac_name: current_by_ac.get(ac_name, Decimal("0.00"))
            - target_by_ac.get(ac_name, Decimal("0.00"))
            for ac_name in all_asset_classes
        }

    @classmethod
    def load_for_user(cls, user: CustomUser) -> Portfolio:
        """Factory method to load a complete portfolio for a user."""

        from portfolio.models import Account

        accounts = list(Account.objects.get_summary_data(user))
        user_id = user.id
        return cls(user_id=user_id, accounts=accounts)

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.models import Account


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

    @classmethod
    def load_for_user(cls, user: object) -> Portfolio:
        """Factory method to load a complete portfolio for a user."""

        from portfolio.models import Account

        accounts = list(Account.objects.get_summary_data(user))
        user_id = user.id  # type: ignore[attr-defined]
        return cls(user_id=user_id, accounts=accounts)

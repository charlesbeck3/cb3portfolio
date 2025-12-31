"""
Modern allocation calculations module.

Public API:
    - get_presentation_rows(user) -> list[dict]
    - get_holdings_rows(user, account_id) -> list[dict]
    - get_sidebar_data(user) -> SidebarData
    - get_account_totals(user) -> dict[int, Decimal]
"""

from typing import Any

from .types import HoldingRow, PresentationRow, SidebarData

__all__ = [
    "HoldingRow",
    "PresentationRow",
    "SidebarData",
]


# Convenience functions will be added after engine is implemented
def get_presentation_rows(user: Any) -> list[dict]:
    """Get allocation presentation data."""
    from .engine import AllocationEngine

    return AllocationEngine().get_presentation_rows(user)


def get_holdings_rows(user: Any, account_id: int | None = None) -> list[dict]:
    """Get holdings detail data."""
    from .engine import AllocationEngine

    return AllocationEngine().get_holdings_rows(user, account_id)


def get_sidebar_data(user: Any) -> SidebarData:
    """Get sidebar data."""
    from .engine import AllocationEngine

    return AllocationEngine().get_sidebar_data(user)


def get_account_totals(user: Any) -> dict[int, Any]:
    """Get account totals."""
    from .engine import AllocationEngine

    return AllocationEngine().get_account_totals(user)


# Add convenience functions to __all__
__all__.extend(
    [
        "get_presentation_rows",
        "get_holdings_rows",
        "get_sidebar_data",
        "get_account_totals",
    ]
)

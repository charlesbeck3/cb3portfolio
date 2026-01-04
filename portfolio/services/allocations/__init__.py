"""
Modern allocation calculations module.

Public API:
    - AllocationEngine - Main engine class
    - get_presentation_rows(user) -> list[dict]
    - get_holdings_rows(user, account_id) -> list[dict]
    - get_aggregated_holdings_rows(user, target_mode) -> list[dict]
    - get_sidebar_data(user) -> SidebarData
    - get_account_totals(user) -> dict[int, Decimal]
"""

from typing import Any

from .engine import AllocationEngine
from .types import HierarchyLevel, HoldingRow, PresentationRow, SidebarData

__all__ = [
    "AllocationEngine",
    "HierarchyLevel",
    "HoldingRow",
    "PresentationRow",
    "SidebarData",
]


# Convenience functions
def get_presentation_rows(user: Any) -> list[dict]:
    """Get allocation presentation data."""
    return AllocationEngine().get_presentation_rows(user)


def get_holdings_rows(user: Any, account_id: int | None = None) -> list[dict]:
    """Get holdings detail data."""
    return AllocationEngine().get_holdings_rows(user, account_id)


def get_sidebar_data(user: Any) -> SidebarData:
    """Get sidebar data."""
    return AllocationEngine().get_sidebar_data(user)


def get_account_totals(user: Any) -> dict[int, Any]:
    """Get account totals."""
    return AllocationEngine().get_account_totals(user)


def get_aggregated_holdings_rows(user: Any, target_mode: str = "effective") -> list[dict]:
    """Get aggregated holdings across all accounts."""
    return AllocationEngine().get_aggregated_holdings_rows(user, target_mode)


# Add convenience functions to __all__
__all__.extend(
    [
        "get_presentation_rows",
        "get_holdings_rows",
        "get_aggregated_holdings_rows",
        "get_sidebar_data",
        "get_account_totals",
    ]
)

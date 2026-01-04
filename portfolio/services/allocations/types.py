"""Type definitions for allocation calculations."""

from decimal import Decimal
from enum import IntEnum
from typing import Any, TypedDict

# Type aliases (Python 3.12+ syntax)
type AllocationDict = dict[str, Decimal]  # {asset_class_name: target_pct}
type TargetMap = dict[int, AllocationDict]  # {account_id: AllocationDict}
type AccountMetadata = dict[str, Any]


class HierarchyLevel(IntEnum):
    """Standard hierarchy levels for allocation display.

    Used throughout allocation and rebalancing modules to indicate the level
    of aggregation for display rows.

    Values are IntEnum so they can be compared and sorted naturally.
    """

    HOLDING = 999  # Individual security holding
    CATEGORY_SUBTOTAL = 1  # Asset category subtotal (e.g., "US Equities Total")
    GROUP_TOTAL = 0  # Asset group total (e.g., "Equities Total")
    GRAND_TOTAL = -1  # Portfolio-wide total


class AccountTypeMetrics(TypedDict):
    """Metrics for a single account type."""

    id: int
    code: str
    label: str
    actual: float
    actual_pct: float
    effective: float
    effective_pct: float


class PresentationRow(TypedDict):
    """Single row for presentation display."""

    asset_class_name: str
    asset_class_id: int
    group_code: str
    group_label: str
    category_code: str
    category_label: str
    row_type: str
    is_cash: bool
    # Portfolio metrics
    portfolio: dict[str, float]  # actual, actual_pct, effective, etc.
    # Account type metrics
    account_types: list[AccountTypeMetrics]


class HoldingRow(TypedDict):
    """Single holding row for holdings view."""

    row_type: str
    ticker: str
    name: str
    value: float
    target_value: float
    value_variance: float
    shares: float
    target_shares: float
    shares_variance: float
    # UI metadata
    is_holding: bool
    is_subtotal: bool
    is_group_total: bool
    is_grand_total: bool


class SidebarData(TypedDict):
    """Sidebar aggregated data."""

    grand_total: Decimal
    account_totals: dict[int, Decimal]
    account_variances: dict[int, float]
    accounts_by_group: dict[str, dict]
    query_count: int

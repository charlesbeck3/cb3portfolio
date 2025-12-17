from __future__ import annotations

from .allocations import AllocationsView
from .dashboard import DashboardView
from .holdings import HoldingsView
from .strategies import AllocationStrategyCreateView
from .targets import TargetAllocationView

__all__ = [
    "AllocationsView",
    "AllocationStrategyCreateView",
    "DashboardView",
    "HoldingsView",
    "TargetAllocationView",
]

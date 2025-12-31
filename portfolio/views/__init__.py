from __future__ import annotations

from .dashboard import DashboardView
from .health import HealthCheckView
from .holdings import HoldingsView, TickerAccountDetailsView
from .strategies import AllocationStrategyCreateView, AllocationStrategyUpdateView
from .targets import TargetAllocationView

__all__ = [
    "AllocationStrategyCreateView",
    "AllocationStrategyUpdateView",
    "DashboardView",
    "HealthCheckView",
    "HoldingsView",
    "TargetAllocationView",
    "TickerAccountDetailsView",
]

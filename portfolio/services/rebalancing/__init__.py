"""Rebalancing calculation engine for portfolio optimization.

This module provides functionality to generate rebalancing recommendations
for portfolio accounts, using cvxpy optimization with proportional fallback.

Usage:
    from portfolio.services.rebalancing import RebalancingEngine

    engine = RebalancingEngine(account)
    plan = engine.generate_plan()

    for order in plan.orders:
        print(f"{order.action} {order.shares} {order.security.ticker}")
"""

from portfolio.services.rebalancing.dataclasses import (
    ProFormaHolding,
    RebalancingOrder,
    RebalancingPlan,
)
from portfolio.services.rebalancing.engine import RebalancingEngine

__all__ = ["ProFormaHolding", "RebalancingEngine", "RebalancingOrder", "RebalancingPlan"]

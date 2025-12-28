"""
Portfolio Django Models

Organized by domain:
- assets.py: Asset classes and categories
- accounts.py: Institutions, account types, and accounts
- securities.py: Securities and holdings
- strategies.py: Allocation strategies and targets
- portfolio.py: Portfolio container
- rebalancing.py: Rebalancing recommendations
"""

from __future__ import annotations

from . import signals  # Register signals

__all__ = [
    "AssetClassCategory",
    "AssetClass",
    "Institution",
    "AccountGroup",
    "AccountType",
    "Account",
    "Security",
    "Holding",
    "AllocationStrategy",
    "TargetAllocation",
    "AccountTypeStrategyAssignment",
    "Portfolio",
    "RebalancingRecommendation",
    "signals",
]
from .accounts import Account, AccountGroup, AccountType, Institution

# Import in dependency order (models with no FKs first)
from .assets import AssetClass, AssetClassCategory
from .portfolio import Portfolio
from .rebalancing import RebalancingRecommendation
from .securities import Holding, Security, SecurityPrice
from .strategies import (
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    TargetAllocation,
)

# Django needs __all__ to register models properly
__all__ = [
    # Assets
    "AssetClass",
    "AssetClassCategory",
    # Accounts
    "Account",
    "AccountGroup",
    "AccountType",
    "Institution",
    # Securities
    "Holding",
    "Security",
    "SecurityPrice",
    # Strategies
    "AccountTypeStrategyAssignment",
    "AllocationStrategy",
    "TargetAllocation",
    # Portfolio
    "Portfolio",
    # Rebalancing
    "RebalancingRecommendation",
]

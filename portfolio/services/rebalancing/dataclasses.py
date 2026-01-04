"""Data structures for rebalancing calculations."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from portfolio.models import Account, AssetClass, Security


@dataclass(frozen=True)
class RebalancingOrder:
    """Represents a single buy or sell order.

    Attributes:
        security: The security to trade
        action: Whether to BUY or SELL
        shares: Number of whole shares to trade
        estimated_amount: Estimated dollar amount (shares * price)
        price_per_share: Price used for estimation
        asset_class: Asset class this security belongs to
    """

    security: "Security"
    action: Literal["BUY", "SELL"]
    shares: int
    estimated_amount: Decimal
    price_per_share: Decimal
    asset_class: "AssetClass"

    def __post_init__(self) -> None:
        """Validate order data."""
        if self.shares <= 0:
            raise ValueError(f"Shares must be positive, got {self.shares}")
        if self.estimated_amount < 0:
            raise ValueError(f"Amount must be non-negative, got {self.estimated_amount}")


@dataclass(frozen=True)
class RebalancingPlan:
    """Complete rebalancing plan for an account.

    Attributes:
        account: The account being rebalanced
        orders: List of buy/sell orders
        proforma_holdings_rows: Formatted rows for template display (with hierarchy)
        drift_analysis_rows: Formatted drift rows with category subtotals
        current_aggregated: Aggregated allocation data for current state
        proforma_aggregated: Aggregated allocation data for pro forma state
        pre_drift: Asset class drift before rebalancing (% points from target)
        post_drift: Estimated drift after rebalancing
        total_buy_amount: Sum of all buy orders
        total_sell_amount: Sum of all sell orders
        net_cash_impact: Negative if cash needed, positive if cash freed
        generated_at: When this plan was calculated
        optimization_status: Status from optimizer
        method_used: 'optimization' or 'proportional' fallback
    """

    account: "Account"
    orders: list[RebalancingOrder] = field(default_factory=list)
    proforma_holdings_rows: list[dict] = field(default_factory=list)
    drift_analysis_rows: list[dict] = field(default_factory=list)
    current_aggregated: dict = field(default_factory=dict)
    proforma_aggregated: dict = field(default_factory=dict)
    pre_drift: dict["AssetClass", Decimal] = field(default_factory=dict)
    post_drift: dict["AssetClass", Decimal] = field(default_factory=dict)
    total_buy_amount: Decimal = Decimal("0")
    total_sell_amount: Decimal = Decimal("0")
    net_cash_impact: Decimal = Decimal("0")
    generated_at: datetime = field(default_factory=datetime.now)
    optimization_status: str = ""
    method_used: Literal["optimization", "proportional"] = "proportional"

    @property
    def buy_orders(self) -> list[RebalancingOrder]:
        """Get only buy orders."""
        return [o for o in self.orders if o.action == "BUY"]

    @property
    def sell_orders(self) -> list[RebalancingOrder]:
        """Get only sell orders."""
        return [o for o in self.orders if o.action == "SELL"]

    @property
    def max_drift_improvement(self) -> Decimal:
        """Calculate maximum drift improvement (pre - post)."""
        if not self.pre_drift or not self.post_drift:
            return Decimal("0")
        pre_max = max(abs(d) for d in self.pre_drift.values())
        post_max = max(abs(d) for d in self.post_drift.values())
        return pre_max - post_max

"""Core rebalancing calculation logic using cvxpy optimization."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

import cvxpy as cp
import numpy as np
import pandas as pd

from portfolio.services.rebalancing.dataclasses import RebalancingOrder

if TYPE_CHECKING:
    from portfolio.models import Account, AssetClass, Holding, Security

logger = logging.getLogger(__name__)


class RebalancingCalculator:
    """Calculates optimal buy/sell orders to rebalance a portfolio.

    Uses cvxpy for optimization with fallback to proportional method.
    Constraints:
    - Whole shares only (integer variables)
    - Non-negative final positions (no shorting)
    """

    def __init__(self, account: Account) -> None:
        """Initialize calculator for given account.

        Args:
            account: The account to rebalance
        """
        self.account = account
        self._holdings_df: pd.DataFrame | None = None
        self._prices: dict[Security, Decimal] = {}
        self._target_allocations: dict[AssetClass, Decimal] = {}

    def calculate_orders(
        self,
        holdings: list[Holding],
        prices: dict[Security, Decimal],
        target_allocations: dict[AssetClass, Decimal],
    ) -> tuple[list[RebalancingOrder], str, Literal["optimization", "proportional"]]:
        """Calculate rebalancing orders.

        Args:
            holdings: Current holdings in the account
            prices: Current prices for all securities
            target_allocations: Target allocation percentages by asset class

        Returns:
            Tuple of (orders, optimization_status, method_used)
        """
        self._holdings_df = self._prepare_holdings_data(holdings, prices, target_allocations)
        self._prices = prices
        self._target_allocations = target_allocations

        # Try optimization first
        try:
            orders = self._optimize_orders()
            return orders, "optimal", "optimization"
        except Exception as e:
            logger.warning(f"Optimization failed: {e}, falling back to proportional")
            orders = self._proportional_orders()
            return orders, "fallback", "proportional"

    def _prepare_holdings_data(
        self,
        holdings: list[Holding],
        prices: dict[Security, Decimal],
        target_allocations: dict[AssetClass, Decimal],
    ) -> pd.DataFrame:
        """Prepare holdings data as DataFrame for calculations.

        Includes asset classes with target allocations but no current holdings,
        using the primary security for that asset class (from the prices dict,
        which already includes primary securities).

        Returns:
            DataFrame with columns: security, asset_class, shares, price, value
        """
        data = []
        existing_asset_class_ids: set[int] = set()

        # Add existing holdings
        for holding in holdings:
            price = prices.get(holding.security, Decimal("0"))
            data.append(
                {
                    "security": holding.security,
                    "security_id": holding.security.id,
                    "asset_class": holding.security.asset_class,
                    "asset_class_id": holding.security.asset_class.id,
                    "shares": float(holding.shares),
                    "price": float(price),
                    "value": float(holding.shares * price),
                }
            )
            existing_asset_class_ids.add(holding.security.asset_class.id)

        # Build map of securities by asset class from prices dict
        # This ensures we use the same Security instances that are in prices
        securities_by_asset_class: dict[int, Security] = {}
        for security in prices:
            ac_id = security.asset_class_id
            # Only track the first (primary) security per asset class
            if ac_id not in securities_by_asset_class:
                securities_by_asset_class[ac_id] = security

        # Add asset classes with targets but no holdings
        for asset_class, target_pct in target_allocations.items():
            if target_pct > 0 and asset_class.id not in existing_asset_class_ids:
                # Get security from prices dict (already includes primary securities)
                primary_security = securities_by_asset_class.get(asset_class.id)
                if primary_security:
                    price = prices.get(primary_security, Decimal("0"))
                    if price > 0:
                        data.append(
                            {
                                "security": primary_security,
                                "security_id": primary_security.id,
                                "asset_class": asset_class,
                                "asset_class_id": asset_class.id,
                                "shares": 0.0,
                                "price": float(price),
                                "value": 0.0,
                            }
                        )
                        logger.info(
                            "added_zero_holding_security",
                            ticker=primary_security.ticker,
                            asset_class=asset_class.name,
                        )

        return pd.DataFrame(data)

    def _get_primary_security_for_asset_class(self, asset_class: AssetClass) -> Security | None:
        """Get the primary security for an asset class.

        Uses the is_primary flag if available, otherwise returns the first security
        in the asset class ordered by ticker.

        Args:
            asset_class: The asset class to get primary security for

        Returns:
            Primary security or None if no securities exist for this asset class
        """
        from portfolio.models import Security

        # First try to get a security marked as primary
        primary = Security.objects.filter(
            asset_class=asset_class,
            is_primary=True,
        ).first()

        if primary:
            return primary

        # Fall back to first security by ticker
        return (
            Security.objects.filter(
                asset_class=asset_class,
            )
            .order_by("ticker")
            .first()
        )

    def _optimize_orders(self) -> list[RebalancingOrder]:
        """Use cvxpy to find optimal buy/sell orders.

        Minimizes sum of squared deviations from target allocations.

        Returns:
            List of rebalancing orders
        """
        df = self._holdings_df
        if df is None or df.empty:
            return []

        total_value = df["value"].sum()
        if total_value == 0:
            return []

        # Group securities by asset class
        securities_by_class = df.groupby("asset_class_id")["security_id"].apply(list).to_dict()

        # Create variables for share changes (can be positive or negative)
        security_ids = df["security_id"].tolist()
        n_securities = len(security_ids)
        share_changes = cp.Variable(n_securities, integer=True)

        # Map security_id to index for variable lookup
        sec_idx = {sec_id: i for i, sec_id in enumerate(security_ids)}

        # Calculate final positions and values
        current_shares = df["shares"].values
        prices_arr = df["price"].values
        final_shares = current_shares + share_changes
        final_values = cp.multiply(final_shares, prices_arr)

        # Build objective: minimize squared deviations from targets
        deviations = []
        final_total = cp.sum(final_values)

        for asset_class, target_pct in self._target_allocations.items():
            # Sum values for all securities in this asset class
            sec_ids = securities_by_class.get(asset_class.id, [])
            if not sec_ids:
                continue

            indices = [sec_idx[sid] for sid in sec_ids if sid in sec_idx]
            if not indices:
                continue

            class_value = cp.sum([final_values[i] for i in indices])
            class_pct = class_value / final_total
            target_decimal = float(target_pct) / 100  # Convert to decimal
            deviation = class_pct - target_decimal
            deviations.append(cp.square(deviation))  # type: ignore[no-untyped-call]

        if not deviations:
            return []

        objective = cp.Minimize(cp.sum(deviations))

        # Constraints
        constraints = [
            final_shares >= 0,  # No shorting
            final_total >= total_value * 0.99,  # Don't lose more than 1% to rounding
        ]

        # Solve
        problem = cp.Problem(objective, constraints)
        try:
            problem.solve(solver=cp.GLPK_MI, verbose=False)  # type: ignore[no-untyped-call]
        except cp.error.SolverError:
            # Try alternate solver if GLPK_MI not available
            problem.solve(verbose=False)  # type: ignore[no-untyped-call]

        if problem.status not in ["optimal", "optimal_inaccurate"]:
            raise ValueError(f"Optimization failed with status: {problem.status}")

        # Extract orders from solution
        orders = []
        share_values = share_changes.value
        if share_values is None:
            return []

        for i, sec_id in enumerate(security_ids):
            change = int(np.round(share_values[i]))
            if change == 0:
                continue

            row = df[df["security_id"] == sec_id].iloc[0]
            security = row["security"]
            price = Decimal(str(row["price"]))

            action: Literal["BUY", "SELL"] = "BUY" if change > 0 else "SELL"
            shares = abs(change)
            amount = Decimal(shares) * price

            orders.append(
                RebalancingOrder(
                    security=security,
                    action=action,
                    shares=shares,
                    estimated_amount=amount,
                    price_per_share=price,
                    asset_class=row["asset_class"],
                )
            )

        return orders

    def _proportional_orders(self) -> list[RebalancingOrder]:
        """Fallback: proportional distribution of needed adjustments.

        For each asset class that's off target:
        - Calculate dollar adjustment needed
        - Distribute across existing holdings proportionally
        - Round to whole shares

        Returns:
            List of rebalancing orders
        """
        df = self._holdings_df
        if df is None or df.empty:
            return []

        total_value = df["value"].sum()
        if total_value == 0:
            return []

        # Calculate current allocations by asset class
        current_alloc = df.groupby("asset_class_id")["value"].sum() / total_value * 100

        # Calculate adjustments needed
        adjustments: dict[int, float] = {}  # asset_class_id -> dollar amount needed
        for asset_class, target_pct in self._target_allocations.items():
            current_pct = current_alloc.get(asset_class.id, 0)
            diff_pct = float(target_pct) - current_pct
            dollar_adjustment = (diff_pct / 100) * total_value
            adjustments[asset_class.id] = dollar_adjustment

        # Generate orders
        orders = []
        for asset_class_id, adjustment in adjustments.items():
            if abs(adjustment) < 1:  # Skip tiny adjustments
                continue

            # Get securities in this asset class
            class_holdings = df[df["asset_class_id"] == asset_class_id]
            if class_holdings.empty:
                continue

            # Distribute proportionally by current value
            class_total = class_holdings["value"].sum()

            for _, row in class_holdings.iterrows():
                proportion = (
                    row["value"] / class_total if class_total > 0 else 1 / len(class_holdings)
                )
                security_adjustment = adjustment * proportion

                price = Decimal(str(row["price"]))
                if price == 0:
                    continue

                shares_float = security_adjustment / float(price)
                shares = int(round(shares_float))

                if shares == 0:
                    continue

                action: Literal["BUY", "SELL"] = "BUY" if shares > 0 else "SELL"
                abs_shares = abs(shares)
                amount = Decimal(abs_shares) * price

                orders.append(
                    RebalancingOrder(
                        security=row["security"],
                        action=action,
                        shares=abs_shares,
                        estimated_amount=amount,
                        price_per_share=price,
                        asset_class=row["asset_class"],
                    )
                )

        return orders

"""High-level orchestration for rebalancing calculations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from portfolio.services.rebalancing.calculator import RebalancingCalculator
from portfolio.services.rebalancing.dataclasses import RebalancingOrder, RebalancingPlan

if TYPE_CHECKING:
    import pandas as pd

    from portfolio.models import Account, AssetClass, Holding, Security

logger = structlog.get_logger(__name__)


class RebalancingEngine:
    """Orchestrates rebalancing plan generation for an account."""

    def __init__(self, account: Account) -> None:
        """Initialize engine for given account.

        Args:
            account: The account to rebalance
        """
        self.account = account
        self.calculator = RebalancingCalculator(account)

    def generate_plan(self) -> RebalancingPlan:
        """Generate a complete rebalancing plan.

        Returns:
            RebalancingPlan with orders and impact analysis
        """
        logger.info(
            "generating_rebalancing_plan",
            account_id=self.account.id,
            account_name=self.account.name,
        )

        # Get target allocations first (needed for fetching primary security prices)
        target_allocations = self._get_target_allocations()

        if not target_allocations:
            logger.info("no_targets_defined", account_id=self.account.id)
            return RebalancingPlan(
                account=self.account,
                orders=[],
                pre_drift={},
                post_drift={},
                total_buy_amount=Decimal("0"),
                total_sell_amount=Decimal("0"),
                net_cash_impact=Decimal("0"),
                generated_at=datetime.now(),
                optimization_status="no_targets",
                method_used="proportional",
            )

        # Get current holdings
        holdings = list(self.account.holdings.select_related("security", "security__asset_class"))

        if not holdings:
            logger.info("no_holdings_to_rebalance", account_id=self.account.id)
            return RebalancingPlan(
                account=self.account,
                orders=[],
                pre_drift={},
                post_drift={},
                total_buy_amount=Decimal("0"),
                total_sell_amount=Decimal("0"),
                net_cash_impact=Decimal("0"),
                generated_at=datetime.now(),
                optimization_status="no_holdings",
                method_used="proportional",
            )

        # Get current prices (includes primary securities for unheld asset classes)
        prices = self._get_current_prices(holdings, target_allocations)

        # Calculate pre-rebalancing drift
        pre_drift = self._calculate_drift(holdings, prices, target_allocations)

        # Generate orders
        orders, status, method = self.calculator.calculate_orders(
            holdings=holdings,
            prices=prices,
            target_allocations=target_allocations,
        )

        # Calculate post-rebalancing drift (estimated)
        post_drift = self._calculate_post_rebalance_drift(
            holdings=holdings,
            orders=orders,
            prices=prices,
            targets=target_allocations,
        )

        # Calculate pro forma holdings with aggregations
        proforma_holdings_rows, current_aggregated, proforma_aggregated = (
            self._calculate_proforma_holdings_with_aggregations(
                holdings=holdings,
                orders=orders,
                prices=prices,
                target_allocations=target_allocations,
            )
        )

        # Format drift analysis with category subtotals
        drift_analysis_rows = self.get_drift_analysis_rows(
            pre_drift=pre_drift,
            post_drift=post_drift,
            target_allocations=target_allocations,
        )

        # Calculate totals
        total_buy = sum((o.estimated_amount for o in orders if o.action == "BUY"), Decimal("0"))
        total_sell = sum((o.estimated_amount for o in orders if o.action == "SELL"), Decimal("0"))

        logger.info(
            "rebalancing_plan_generated",
            account_id=self.account.id,
            order_count=len(orders),
            total_buy=float(total_buy),
            total_sell=float(total_sell),
            method=method,
            status=status,
        )

        return RebalancingPlan(
            account=self.account,
            orders=orders,
            proforma_holdings_rows=proforma_holdings_rows,
            drift_analysis_rows=drift_analysis_rows,
            current_aggregated=current_aggregated,
            proforma_aggregated=proforma_aggregated,
            pre_drift=pre_drift,
            post_drift=post_drift,
            total_buy_amount=total_buy,
            total_sell_amount=total_sell,
            net_cash_impact=total_sell - total_buy,
            generated_at=datetime.now(),
            optimization_status=status,
            method_used=method,
        )

    def get_proforma_holdings_rows(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
        prices: dict[Security, Decimal],
        target_allocations: dict[AssetClass, Decimal],
    ) -> list[dict]:
        """
        Format pro forma holdings for template display.

        Uses the SAME AllocationCalculator and AllocationFormatter as the
        allocation views to ensure consistent calculation logic and display format.

        The resulting rows have the standard hierarchy structure:
        - hierarchy_level 999: Individual holdings
        - hierarchy_level 1: Category subtotals
        - hierarchy_level 0: Group totals
        - hierarchy_level -1: Grand total

        Args:
            holdings: Current holdings before rebalancing
            orders: Orders to apply
            prices: Current security prices
            target_allocations: Target allocations by asset class

        Returns:
            List of row dicts with hierarchy_level field for template rendering.
            Same format as AllocationEngine.get_holdings_rows().
        """
        from portfolio.services.allocations.calculations import AllocationCalculator
        from portfolio.services.allocations.formatters import AllocationFormatter

        if not holdings and not orders:
            return []

        # Build pro forma holdings DataFrame by applying orders
        proforma_df = self._build_proforma_holdings_dataframe(holdings, orders, prices)

        if proforma_df.empty:
            return []

        # Build targets map in the format expected by AllocationCalculator
        targets_map = {
            self.account.id: {
                asset_class.name: float(target_pct)
                for asset_class, target_pct in target_allocations.items()
            }
        }

        # Use AllocationCalculator to add targets and variances
        calculator = AllocationCalculator()
        holdings_with_targets = calculator.calculate_holdings_with_targets(
            holdings_df=proforma_df,
            targets_map=targets_map,
        )

        # Use AllocationFormatter to format rows with hierarchy
        formatter = AllocationFormatter()
        rows = formatter.format_holdings_rows(holdings_with_targets)

        return rows

    def get_drift_analysis_rows(
        self,
        pre_drift: dict[AssetClass, Decimal],
        post_drift: dict[AssetClass, Decimal],
        target_allocations: dict[AssetClass, Decimal],
    ) -> list[dict]:
        """
        Format drift data with category subtotals.

        Delegates to AllocationFormatter for consistent formatting with other
        allocation views.

        Args:
            pre_drift: Pre-rebalance drift by asset class
            post_drift: Post-rebalance drift by asset class
            target_allocations: Target allocations by asset class

        Returns:
            List of row dicts with hierarchy levels for template rendering
        """
        from portfolio.services.allocations.formatters import AllocationFormatter

        formatter = AllocationFormatter()
        return formatter.format_drift_analysis_rows(
            pre_drift=pre_drift,
            post_drift=post_drift,
            target_allocations=target_allocations,
        )

    def _get_current_prices(
        self,
        holdings: list[Holding],
        target_allocations: dict[AssetClass, Decimal],
    ) -> dict[Security, Decimal]:
        """Get current prices for all securities in the account.

        Includes prices for primary securities in target asset classes
        even if not currently held. Delegates to DjangoDataProvider for
        consistent price fetching across the application.
        """
        from portfolio.services.allocations.data_providers import DjangoDataProvider

        securities: set[Security] = {h.security for h in holdings}

        provider = DjangoDataProvider()
        prices = provider.get_security_prices(
            securities=securities,
            include_primary_for_asset_classes=set(target_allocations.keys()),
        )

        # Log warnings for missing prices
        for security, price in prices.items():
            if price == Decimal("0"):
                logger.warning(
                    "no_price_found",
                    ticker=security.ticker,
                    security_id=security.id,
                )

        return prices

    def _get_target_allocations(self) -> dict[AssetClass, Decimal]:
        """Get target allocations for this account.

        Uses the account's effective allocation strategy (account-level,
        account-type-level, or portfolio-level fallback).
        """
        strategy = self.account.get_effective_allocation_strategy()
        if not strategy:
            return {}

        # Get allocations from strategy
        targets: dict[AssetClass, Decimal] = {}
        for target_alloc in strategy.target_allocations.select_related("asset_class"):
            targets[target_alloc.asset_class] = target_alloc.target_percent

        return targets

    def _build_holdings_dataframe(
        self,
        holdings: list[Holding],
        prices: dict[Security, Decimal],
    ) -> pd.DataFrame:
        """
        Build a holdings DataFrame for use with AllocationCalculator.

        Delegates to DjangoDataProvider.holdings_to_dataframe() for consistent
        DataFrame schema across allocation and rebalancing modules.

        Args:
            holdings: List of Holding model objects
            prices: Dict mapping Security to current price

        Returns:
            DataFrame with standard holdings schema
        """
        from portfolio.services.allocations.data_providers import DjangoDataProvider

        provider = DjangoDataProvider()
        return provider.holdings_to_dataframe(
            holdings=holdings,
            prices=prices,
            account_id=self.account.id,
        )

    def _build_targets_map(
        self,
        targets: dict[AssetClass, Decimal],
    ) -> dict[int, dict[str, float]]:
        """
        Build a targets map for use with AllocationCalculator.

        Args:
            targets: Dict mapping AssetClass to target percentage

        Returns:
            Dict in format {account_id: {asset_class_name: target_pct}}
        """
        return {
            self.account.id: {
                asset_class.name: float(target_pct) for asset_class, target_pct in targets.items()
            }
        }

    def _calculate_drift_from_dataframe(
        self,
        holdings_df: pd.DataFrame,
        targets: dict[AssetClass, Decimal],
    ) -> dict[AssetClass, Decimal]:
        """
        Calculate asset-class level drift from a holdings DataFrame.

        Shared logic for both pre-rebalancing and post-rebalancing drift calculation.
        Uses AllocationCalculator.calculate_holdings_with_targets() which already
        calculates Allocation_Variance_Pct - drift IS variance!

        Args:
            holdings_df: Holdings DataFrame with standard schema
            targets: Target allocation percentages by asset class

        Returns:
            Dict mapping AssetClass to drift percentage (positive = over target)
        """
        from portfolio.services.allocations.calculations import AllocationCalculator

        if holdings_df.empty:
            # Return negative target for each asset class (100% underweight)
            return {ac: -target_pct for ac, target_pct in targets.items()}

        # Build targets map using shared helper
        targets_map = self._build_targets_map(targets)

        # Use AllocationCalculator - it already calculates variance/drift!
        calculator = AllocationCalculator()
        holdings_with_targets = calculator.calculate_holdings_with_targets(
            holdings_df=holdings_df,
            targets_map=targets_map,
        )

        # Check for zero total value
        total_value = holdings_with_targets["Value"].sum()
        if total_value == 0:
            return {ac: -target_pct for ac, target_pct in targets.items()}

        # Drift IS variance! Just aggregate Allocation_Variance_Pct by asset class
        ac_variance = (
            holdings_with_targets.groupby(["Asset_Class_ID", "Asset_Class"])[
                "Allocation_Variance_Pct"
            ]
            .sum()
            .reset_index()
        )

        # Build drift dict with Decimal precision for financial calculations
        drift: dict[AssetClass, Decimal] = {}
        for asset_class, target_pct in targets.items():
            ac_rows = ac_variance[ac_variance["Asset_Class_ID"] == asset_class.id]
            if not ac_rows.empty:
                variance_pct = ac_rows["Allocation_Variance_Pct"].iloc[0]
                drift[asset_class] = Decimal(str(round(variance_pct, 6)))
            else:
                # Asset class not in current holdings - drift is -target
                drift[asset_class] = -target_pct

        return drift

    def _calculate_drift(
        self,
        holdings: list[Holding],
        prices: dict[Security, Decimal],
        targets: dict[AssetClass, Decimal],
    ) -> dict[AssetClass, Decimal]:
        """
        Calculate drift (current % - target %) for each asset class.

        Uses AllocationCalculator infrastructure for consistent calculation logic
        with the allocation views, then aggregates to asset-class level.

        Args:
            holdings: Current holdings
            prices: Current security prices
            targets: Target allocation percentages by asset class

        Returns:
            Dict mapping AssetClass to drift percentage (positive = over target)
        """
        if not holdings:
            return {}

        # Build DataFrame using shared helper
        holdings_df = self._build_holdings_dataframe(holdings, prices)

        # Delegate to shared drift calculation
        return self._calculate_drift_from_dataframe(holdings_df, targets)

    def _apply_orders_to_positions(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
    ) -> dict[Security, Decimal]:
        """
        Apply orders to holdings to create pro forma position map.

        Args:
            holdings: Current holdings
            orders: Orders to apply

        Returns:
            Dict mapping Security to pro forma share count (positive values only)
        """
        # Build position map: security -> shares
        positions: dict[Security, Decimal] = {h.security: h.shares for h in holdings}

        # Apply orders
        for order in orders:
            current = positions.get(order.security, Decimal("0"))
            if order.action == "BUY":
                positions[order.security] = current + Decimal(order.shares)
            else:  # SELL
                positions[order.security] = current - Decimal(order.shares)

        # Filter out zero/negative positions
        return {sec: shares for sec, shares in positions.items() if shares > 0}

    def _build_proforma_holdings_dataframe(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
        prices: dict[Security, Decimal],
    ) -> pd.DataFrame:
        """
        Build a pro forma holdings DataFrame after applying orders.

        Applies buy/sell orders to current holdings to create the expected
        post-rebalance position for drift calculation. Delegates to
        DjangoDataProvider.securities_to_dataframe() for consistent schema.

        Args:
            holdings: Current holdings
            orders: Orders to apply
            prices: Current security prices

        Returns:
            DataFrame with pro forma positions (same schema as _build_holdings_dataframe)
        """
        from portfolio.services.allocations.data_providers import DjangoDataProvider

        # Apply orders to get pro forma positions
        positions = self._apply_orders_to_positions(holdings, orders)

        # Use shared helper to build DataFrame
        provider = DjangoDataProvider()
        return provider.securities_to_dataframe(
            positions=positions,
            prices=prices,
            account_id=self.account.id,
        )

    def _calculate_post_rebalance_drift(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
        prices: dict[Security, Decimal],
        targets: dict[AssetClass, Decimal],
    ) -> dict[AssetClass, Decimal]:
        """
        Calculate estimated post-rebalance drift.

        Applies orders to current holdings and calculates resulting drift.
        Uses AllocationCalculator infrastructure for consistent calculation logic.

        Note: This is approximate since actual execution prices may differ.

        Args:
            holdings: Current holdings
            orders: Orders to apply
            prices: Current security prices
            targets: Target allocation percentages by asset class

        Returns:
            Dict mapping AssetClass to expected post-rebalance drift percentage
        """
        if not holdings and not orders:
            return {ac: -target_pct for ac, target_pct in targets.items()}

        # Build pro forma holdings DataFrame
        proforma_df = self._build_proforma_holdings_dataframe(holdings, orders, prices)

        # Delegate to shared drift calculation
        return self._calculate_drift_from_dataframe(proforma_df, targets)

    def _calculate_proforma_holdings_with_aggregations(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
        prices: dict[Security, Decimal],
        target_allocations: dict[AssetClass, Decimal],
    ) -> tuple[list[dict], dict, dict]:
        """
        Calculate pro forma holdings with aggregated allocation data.

        Uses AllocationCalculator and AllocationFormatter for all calculations,
        ensuring consistency with allocation views.

        Args:
            holdings: Current holdings
            orders: Orders to apply
            prices: Current security prices
            target_allocations: Target allocation percentages by asset class

        Returns:
            Tuple of:
            - proforma_holdings_rows: List of formatted row dicts (with hierarchy)
            - current_aggregated: Dict with current allocations by asset class
            - proforma_aggregated: Dict with pro forma allocations by asset class
        """
        import pandas as pd

        from portfolio.models import AssetClass
        from portfolio.services.allocations.calculations import AllocationCalculator

        # Build map of current holdings: security -> shares
        current_positions = {h.security: h.shares for h in holdings}

        # Build map of changes from orders: security -> share change
        changes: dict[Security, int] = {}
        for order in orders:
            current_change = changes.get(order.security, 0)
            if order.action == "BUY":
                changes[order.security] = current_change + order.shares
            else:  # SELL
                changes[order.security] = current_change - order.shares

        # Get all securities involved (current holdings + new positions from orders)
        all_securities = set(current_positions.keys()) | set(changes.keys())

        # Get asset class metadata for aggregation
        asset_class_ids = {s.asset_class.id for s in all_securities}
        asset_classes_df = pd.DataFrame(
            [
                {
                    "asset_class_id": ac.id,
                    "asset_class_name": ac.name,
                }
                for ac in AssetClass.objects.filter(id__in=asset_class_ids)
            ]
        )

        calculator = AllocationCalculator()

        # ========================================================================
        # Calculate CURRENT allocations using existing allocation infrastructure
        # ========================================================================

        if current_positions:
            current_data = []
            for security in all_securities:
                shares = current_positions.get(security, Decimal("0"))
                price = prices.get(security, Decimal("0"))
                value = shares * price

                current_data.append(
                    {
                        "security_id": security.id,
                        "asset_class_id": security.asset_class.id,
                        "value": float(value),
                    }
                )

            current_holdings_df = pd.DataFrame(current_data)

            # Use existing aggregation method from AllocationCalculator
            current_aggregated_df = calculator._aggregate_actuals_by_level(
                df=asset_classes_df, holdings_df=current_holdings_df, level="portfolio"
            )

            # Convert to dict format for backward compatibility
            current_aggregated = calculator.aggregated_df_to_dict(current_aggregated_df)
        else:
            current_aggregated = {
                "asset_class": {},
                "grand_total": {"total_value": Decimal("0"), "allocation_percent": Decimal("0")},
            }

        # ========================================================================
        # Calculate PRO FORMA allocations using same infrastructure
        # ========================================================================

        proforma_data = []
        for security in all_securities:
            current_shares = current_positions.get(security, Decimal("0"))
            change_shares = changes.get(security, 0)
            proforma_shares = current_shares + Decimal(change_shares)
            price = prices.get(security, Decimal("0"))
            proforma_value = proforma_shares * price

            proforma_data.append(
                {
                    "security_id": security.id,
                    "asset_class_id": security.asset_class.id,
                    "value": float(proforma_value),
                }
            )

        if proforma_data:
            proforma_holdings_df = pd.DataFrame(proforma_data)

            # Use existing aggregation method
            proforma_aggregated_df = calculator._aggregate_actuals_by_level(
                df=asset_classes_df, holdings_df=proforma_holdings_df, level="portfolio"
            )

            # Convert to dict format
            proforma_aggregated = calculator.aggregated_df_to_dict(proforma_aggregated_df)
        else:
            proforma_aggregated = {
                "asset_class": {},
                "grand_total": {"total_value": Decimal("0"), "allocation_percent": Decimal("0")},
            }

        # ========================================================================
        # Build pro forma holdings rows using get_proforma_holdings_rows
        # ========================================================================

        proforma_holdings_rows = self.get_proforma_holdings_rows(
            holdings=holdings,
            orders=orders,
            prices=prices,
            target_allocations=target_allocations,
        )

        return (proforma_holdings_rows, current_aggregated, proforma_aggregated)

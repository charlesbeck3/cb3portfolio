"""High-level orchestration for rebalancing calculations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from portfolio.services.rebalancing.calculator import RebalancingCalculator
from portfolio.services.rebalancing.dataclasses import (
    ProFormaHolding,
    RebalancingOrder,
    RebalancingPlan,
)

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
                proforma_holdings=[],
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
                proforma_holdings=[],
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

        # Calculate post-rebalancing state (estimated)
        post_drift = self._estimate_post_drift(
            holdings=holdings,
            orders=orders,
            prices=prices,
            targets=target_allocations,
        )

        # Calculate pro forma holdings
        proforma_holdings, current_aggregated, proforma_aggregated = (
            self._calculate_proforma_holdings_with_aggregations(
                holdings=holdings,
                orders=orders,
                prices=prices,
                target_allocations=target_allocations,
            )
        )

        # Format pro forma holdings for template display
        proforma_holdings_rows = self.get_proforma_holdings_rows(
            proforma_holdings=proforma_holdings,
            target_allocations=target_allocations,
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
            proforma_holdings=proforma_holdings,
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
        proforma_holdings: list[ProFormaHolding],
        target_allocations: dict[AssetClass, Decimal],
    ) -> list[dict]:
        """
        Convert pro forma holdings to structured rows with hierarchy.

        Uses the same AllocationCalculator and AllocationFormatter as the
        holdings view to ensure consistent grouping and display.

        Args:
            proforma_holdings: List of ProFormaHolding objects
            target_allocations: Target allocations by asset class

        Returns:
            List of row dicts with hierarchy_level field for template rendering
        """
        import pandas as pd

        from portfolio.services.allocations.calculations import AllocationCalculator
        from portfolio.services.allocations.formatters import AllocationFormatter

        if not proforma_holdings:
            return []

        # Convert ProFormaHolding list to DataFrame format
        holdings_data = []
        for pf in proforma_holdings:
            holdings_data.append(
                {
                    "Ticker": pf.security.ticker,
                    "Security_Name": pf.security.name,
                    "Asset_Class": pf.asset_class.name,
                    "Asset_Class_ID": pf.asset_class.id,
                    "Category_Code": pf.asset_class.category.code,
                    "Category_Sort_Order": pf.asset_class.category.sort_order
                    if hasattr(pf.asset_class.category, "sort_order")
                    else 0,
                    "Asset_Category": pf.asset_class.category.label,
                    "Group_Code": pf.asset_class.category.parent.code
                    if pf.asset_class.category.parent
                    else pf.asset_class.category.code,
                    "Group_Sort_Order": pf.asset_class.category.parent.sort_order
                    if pf.asset_class.category.parent
                    and hasattr(pf.asset_class.category.parent, "sort_order")
                    else 0,
                    "Asset_Group": pf.asset_class.category.parent.label
                    if pf.asset_class.category.parent
                    else pf.asset_class.category.label,
                    "Price": float(pf.price_per_share),
                    "Shares": float(pf.proforma_shares),
                    "Value": float(pf.proforma_value),
                    "Account_ID": self.account.id,
                    "Account_Name": self.account.name,
                    "Account_Type": self.account.account_type.code,
                    "Holding_ID": 0,  # Pro forma holdings don't have IDs
                }
            )

        holdings_df = pd.DataFrame(holdings_data)

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
            holdings_df=holdings_df,
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
        even if not currently held.
        """
        from portfolio.models import Security, SecurityPrice

        prices: dict[Security, Decimal] = {}
        securities: set[Security] = {h.security for h in holdings}

        # Add primary securities from target asset classes
        existing_asset_class_ids = {s.asset_class_id for s in securities}
        for asset_class in target_allocations:
            if asset_class.id not in existing_asset_class_ids:
                # Get primary security for this asset class
                primary = Security.objects.filter(
                    asset_class=asset_class,
                    is_primary=True,
                ).first()

                if not primary:
                    # Fall back to first security by ticker
                    primary = (
                        Security.objects.filter(
                            asset_class=asset_class,
                        )
                        .order_by("ticker")
                        .first()
                    )

                if primary:
                    securities.add(primary)

        # Fetch prices for all securities
        for security in securities:
            latest_price = (
                SecurityPrice.objects.filter(security=security).order_by("-price_datetime").first()
            )

            if latest_price:
                prices[security] = latest_price.price
            else:
                logger.warning(
                    "no_price_found",
                    ticker=security.ticker,
                    security_id=security.id,
                )
                prices[security] = Decimal("0")

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

        This helper method converts Django model objects to the DataFrame format
        expected by the allocation calculation infrastructure, enabling consistent
        calculation logic across rebalancing and allocation views.

        Args:
            holdings: List of Holding model objects
            prices: Dict mapping Security to current price

        Returns:
            DataFrame with columns: Ticker, Security_Name, Asset_Class, Asset_Class_ID,
            Category_Code, Category_Sort_Order, Asset_Category, Group_Code,
            Group_Sort_Order, Asset_Group, Price, Shares, Value, Account_ID
        """
        import pandas as pd

        if not holdings:
            return pd.DataFrame()

        holdings_data = []
        for h in holdings:
            price = prices.get(h.security, Decimal("0"))
            value = h.shares * price
            asset_class = h.security.asset_class
            category = asset_class.category

            holdings_data.append(
                {
                    "Ticker": h.security.ticker,
                    "Security_Name": h.security.name,
                    "Asset_Class": asset_class.name,
                    "Asset_Class_ID": asset_class.id,
                    "Category_Code": category.code,
                    "Category_Sort_Order": getattr(category, "sort_order", 0),
                    "Asset_Category": category.label,
                    "Group_Code": category.parent.code if category.parent else category.code,
                    "Group_Sort_Order": getattr(category.parent, "sort_order", 0)
                    if category.parent
                    else 0,
                    "Asset_Group": category.parent.label if category.parent else category.label,
                    "Price": float(price),
                    "Shares": float(h.shares),
                    "Value": float(value),
                    "Account_ID": self.account.id,
                }
            )

        return pd.DataFrame(holdings_data)

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
        from portfolio.services.allocations.calculations import AllocationCalculator

        if not holdings:
            return {}

        # Build DataFrame using shared helper
        holdings_df = self._build_holdings_dataframe(holdings, prices)

        if holdings_df.empty:
            return {}

        # Build targets map using shared helper
        targets_map = self._build_targets_map(targets)

        # Use AllocationCalculator for consistent calculation logic
        calculator = AllocationCalculator()
        holdings_with_targets = calculator.calculate_holdings_with_targets(
            holdings_df=holdings_df,
            targets_map=targets_map,
        )

        # Aggregate to asset-class level
        # The calculator returns per-security variances; we need asset-class totals
        total_value = holdings_with_targets["Value"].sum()
        if total_value == 0:
            return {}

        # Group by asset class and sum values
        ac_grouped = (
            holdings_with_targets.groupby(["Asset_Class_ID", "Asset_Class"])
            .agg({"Value": "sum", "Target_Value": "sum"})
            .reset_index()
        )

        # Calculate asset-class level allocation percentages
        ac_grouped["Allocation_Pct"] = (ac_grouped["Value"] / total_value) * 100
        ac_grouped["Target_Allocation_Pct"] = (ac_grouped["Target_Value"] / total_value) * 100
        ac_grouped["Variance_Pct"] = (
            ac_grouped["Allocation_Pct"] - ac_grouped["Target_Allocation_Pct"]
        )

        # Build drift dict with Decimal precision for financial calculations
        drift: dict[AssetClass, Decimal] = {}
        for asset_class, target_pct in targets.items():
            ac_rows = ac_grouped[ac_grouped["Asset_Class_ID"] == asset_class.id]
            if not ac_rows.empty:
                variance = ac_rows["Variance_Pct"].iloc[0]
                drift[asset_class] = Decimal(str(round(variance, 6)))
            else:
                # Asset class not in current holdings - drift is -target
                drift[asset_class] = -target_pct

        return drift

    def _build_proforma_holdings_dataframe(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
        prices: dict[Security, Decimal],
    ) -> pd.DataFrame:
        """
        Build a pro forma holdings DataFrame after applying orders.

        Applies buy/sell orders to current holdings to create the expected
        post-rebalance position for drift calculation.

        Args:
            holdings: Current holdings
            orders: Orders to apply
            prices: Current security prices

        Returns:
            DataFrame with pro forma positions (same format as _build_holdings_dataframe)
        """
        import pandas as pd

        # Build position map: security -> shares
        positions: dict[Security, Decimal] = {h.security: h.shares for h in holdings}

        # Apply orders
        for order in orders:
            current = positions.get(order.security, Decimal("0"))
            if order.action == "BUY":
                positions[order.security] = current + Decimal(order.shares)
            else:  # SELL
                positions[order.security] = current - Decimal(order.shares)

        # Build DataFrame from pro forma positions
        holdings_data = []
        for security, shares in positions.items():
            if shares <= 0:
                continue

            price = prices.get(security, Decimal("0"))
            value = shares * price
            asset_class = security.asset_class
            category = asset_class.category

            holdings_data.append(
                {
                    "Ticker": security.ticker,
                    "Security_Name": security.name,
                    "Asset_Class": asset_class.name,
                    "Asset_Class_ID": asset_class.id,
                    "Category_Code": category.code,
                    "Category_Sort_Order": getattr(category, "sort_order", 0),
                    "Asset_Category": category.label,
                    "Group_Code": category.parent.code if category.parent else category.code,
                    "Group_Sort_Order": getattr(category.parent, "sort_order", 0)
                    if category.parent
                    else 0,
                    "Asset_Group": category.parent.label if category.parent else category.label,
                    "Price": float(price),
                    "Shares": float(shares),
                    "Value": float(value),
                    "Account_ID": self.account.id,
                }
            )

        return pd.DataFrame(holdings_data) if holdings_data else pd.DataFrame()

    def _estimate_post_drift(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
        prices: dict[Security, Decimal],
        targets: dict[AssetClass, Decimal],
    ) -> dict[AssetClass, Decimal]:
        """
        Estimate drift after applying orders.

        Uses AllocationCalculator infrastructure for consistent calculation logic.
        This is approximate since actual execution prices may differ.

        Args:
            holdings: Current holdings
            orders: Orders to apply
            prices: Current security prices
            targets: Target allocation percentages by asset class

        Returns:
            Dict mapping AssetClass to expected post-rebalance drift percentage
        """
        from portfolio.services.allocations.calculations import AllocationCalculator

        if not holdings and not orders:
            return {}

        # Build pro forma holdings DataFrame
        proforma_df = self._build_proforma_holdings_dataframe(holdings, orders, prices)

        if proforma_df.empty:
            return {}

        # Build targets map using shared helper
        targets_map = self._build_targets_map(targets)

        # Use AllocationCalculator for consistent calculation logic
        calculator = AllocationCalculator()
        holdings_with_targets = calculator.calculate_holdings_with_targets(
            holdings_df=proforma_df,
            targets_map=targets_map,
        )

        # Aggregate to asset-class level
        total_value = holdings_with_targets["Value"].sum()
        if total_value == 0:
            return {}

        # Group by asset class and sum values
        ac_grouped = (
            holdings_with_targets.groupby(["Asset_Class_ID", "Asset_Class"])
            .agg({"Value": "sum", "Target_Value": "sum"})
            .reset_index()
        )

        # Calculate asset-class level allocation percentages
        ac_grouped["Allocation_Pct"] = (ac_grouped["Value"] / total_value) * 100
        ac_grouped["Target_Allocation_Pct"] = (ac_grouped["Target_Value"] / total_value) * 100
        ac_grouped["Variance_Pct"] = (
            ac_grouped["Allocation_Pct"] - ac_grouped["Target_Allocation_Pct"]
        )

        # Build drift dict with Decimal precision for financial calculations
        drift: dict[AssetClass, Decimal] = {}
        for asset_class, target_pct in targets.items():
            ac_rows = ac_grouped[ac_grouped["Asset_Class_ID"] == asset_class.id]
            if not ac_rows.empty:
                variance = ac_rows["Variance_Pct"].iloc[0]
                drift[asset_class] = Decimal(str(round(variance, 6)))
            else:
                # Asset class not in pro forma holdings - drift is -target
                drift[asset_class] = -target_pct

        return drift

    def _calculate_proforma_holdings_with_aggregations(
        self,
        holdings: list[Holding],
        orders: list[RebalancingOrder],
        prices: dict[Security, Decimal],
        target_allocations: dict[AssetClass, Decimal],
    ) -> tuple[list[ProFormaHolding], dict, dict]:
        """Calculate pro forma holdings with aggregated allocation data.

        Returns:
            Tuple of (proforma_holdings_list, current_aggregated, proforma_aggregated)
        """
        import pandas as pd

        from portfolio.services.allocations.calculations import AllocationAggregator

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

        # Get all securities (current holdings + new positions from orders)
        all_securities = set(current_positions.keys()) | set(changes.keys())

        # Calculate current allocations using existing aggregator
        current_data = []
        for security in all_securities:
            shares = current_positions.get(security, Decimal("0"))
            price = prices.get(security, Decimal("0"))
            value = shares * price

            current_data.append(
                {
                    "security": security,
                    "security_id": security.id,
                    "asset_class": security.asset_class,
                    "asset_class_id": security.asset_class.id,
                    "category": security.asset_class.category,
                    "value": value,
                    "shares": shares,
                    "price": price,
                }
            )

        if not current_data:
            current_aggregated = {}
        else:
            current_df = pd.DataFrame(current_data)
            current_aggregator = AllocationAggregator(current_df)
            current_aggregator.calculate_aggregations()
            current_aggregated = current_aggregator.build_context()

        # Calculate pro forma allocations using existing aggregator
        proforma_data = []
        for security in all_securities:
            current_shares = current_positions.get(security, Decimal("0"))
            change_shares = changes.get(security, 0)
            proforma_shares = current_shares + Decimal(change_shares)
            price = prices.get(security, Decimal("0"))
            proforma_value = proforma_shares * price

            proforma_data.append(
                {
                    "security": security,
                    "security_id": security.id,
                    "asset_class": security.asset_class,
                    "asset_class_id": security.asset_class.id,
                    "category": security.asset_class.category,
                    "value": proforma_value,
                    "shares": proforma_shares,
                    "price": price,
                }
            )

        if not proforma_data:
            proforma_aggregated = {}
        else:
            proforma_df = pd.DataFrame(proforma_data)
            proforma_aggregator = AllocationAggregator(proforma_df)
            proforma_aggregator.calculate_aggregations()
            proforma_aggregated = proforma_aggregator.build_context()

        # Build pro forma holdings list with aggregated allocation data
        proforma_list = []

        for security in sorted(
            all_securities,
            key=lambda s: (s.asset_class.category.code, s.asset_class.name, s.ticker),
        ):
            price = prices.get(security, Decimal("0"))

            # Current state
            current_shares = current_positions.get(security, Decimal("0"))
            current_value = current_shares * price

            # Changes
            change_shares = changes.get(security, 0)
            change_value = Decimal(change_shares) * price

            # Pro forma state
            proforma_shares = current_shares + Decimal(change_shares)
            proforma_value = proforma_shares * price

            # Get asset class level allocations from aggregated data
            asset_class = security.asset_class

            # Current allocation from aggregated data
            current_alloc = Decimal("0")
            if (
                "asset_class" in current_aggregated
                and asset_class.id in current_aggregated["asset_class"]
            ):
                current_alloc = current_aggregated["asset_class"][asset_class.id].get(
                    "allocation_percent", Decimal("0")
                )

            # Pro forma allocation from aggregated data
            proforma_alloc = Decimal("0")
            if (
                "asset_class" in proforma_aggregated
                and asset_class.id in proforma_aggregated["asset_class"]
            ):
                proforma_alloc = proforma_aggregated["asset_class"][asset_class.id].get(
                    "allocation_percent", Decimal("0")
                )

            # Target and variance
            target_alloc = target_allocations.get(asset_class, Decimal("0"))
            variance = proforma_alloc - target_alloc

            proforma_list.append(
                ProFormaHolding(
                    security=security,
                    asset_class=asset_class,
                    current_shares=current_shares,
                    change_shares=change_shares,
                    proforma_shares=proforma_shares,
                    current_value=current_value,
                    change_value=change_value,
                    proforma_value=proforma_value,
                    current_allocation=current_alloc,
                    proforma_allocation=proforma_alloc,
                    target_allocation=target_alloc,
                    variance=variance,
                    price_per_share=price,
                )
            )

        return proforma_list, current_aggregated, proforma_aggregated

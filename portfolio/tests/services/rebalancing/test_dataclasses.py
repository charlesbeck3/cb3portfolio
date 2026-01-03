"""Unit tests for rebalancing dataclasses."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from portfolio.services.rebalancing.dataclasses import RebalancingOrder, RebalancingPlan


class TestRebalancingOrder:
    """Tests for RebalancingOrder dataclass."""

    def test_valid_buy_order(self):
        """Test creating a valid buy order."""
        security = Mock()
        asset_class = Mock()

        order = RebalancingOrder(
            security=security,
            action="BUY",
            shares=10,
            estimated_amount=Decimal("1000.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )

        assert order.action == "BUY"
        assert order.shares == 10
        assert order.estimated_amount == Decimal("1000.00")
        assert order.price_per_share == Decimal("100.00")

    def test_valid_sell_order(self):
        """Test creating a valid sell order."""
        security = Mock()
        asset_class = Mock()

        order = RebalancingOrder(
            security=security,
            action="SELL",
            shares=5,
            estimated_amount=Decimal("500.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )

        assert order.action == "SELL"
        assert order.shares == 5

    def test_invalid_zero_shares_raises(self):
        """Test that zero shares raises ValueError."""
        security = Mock()
        asset_class = Mock()

        with pytest.raises(ValueError, match="Shares must be positive"):
            RebalancingOrder(
                security=security,
                action="BUY",
                shares=0,
                estimated_amount=Decimal("0"),
                price_per_share=Decimal("100.00"),
                asset_class=asset_class,
            )

    def test_invalid_negative_shares_raises(self):
        """Test that negative shares raises ValueError."""
        security = Mock()
        asset_class = Mock()

        with pytest.raises(ValueError, match="Shares must be positive"):
            RebalancingOrder(
                security=security,
                action="SELL",
                shares=-5,
                estimated_amount=Decimal("500.00"),
                price_per_share=Decimal("100.00"),
                asset_class=asset_class,
            )

    def test_invalid_negative_amount_raises(self):
        """Test that negative amount raises ValueError."""
        security = Mock()
        asset_class = Mock()

        with pytest.raises(ValueError, match="Amount must be non-negative"):
            RebalancingOrder(
                security=security,
                action="BUY",
                shares=5,
                estimated_amount=Decimal("-500.00"),
                price_per_share=Decimal("100.00"),
                asset_class=asset_class,
            )

    def test_order_is_frozen(self):
        """Test that order is immutable (frozen dataclass)."""
        security = Mock()
        asset_class = Mock()

        order = RebalancingOrder(
            security=security,
            action="BUY",
            shares=10,
            estimated_amount=Decimal("1000.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )

        with pytest.raises(AttributeError):
            order.shares = 20


class TestRebalancingPlan:
    """Tests for RebalancingPlan dataclass."""

    def test_empty_plan(self):
        """Test creating an empty plan."""
        account = Mock()

        plan = RebalancingPlan(account=account)

        assert plan.orders == []
        assert plan.total_buy_amount == Decimal("0")
        assert plan.total_sell_amount == Decimal("0")
        assert plan.net_cash_impact == Decimal("0")

    def test_plan_with_orders(self):
        """Test plan with buy and sell orders."""
        account = Mock()
        security = Mock()
        asset_class = Mock()

        buy_order = RebalancingOrder(
            security=security,
            action="BUY",
            shares=10,
            estimated_amount=Decimal("1000.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )
        sell_order = RebalancingOrder(
            security=security,
            action="SELL",
            shares=5,
            estimated_amount=Decimal("500.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )

        plan = RebalancingPlan(
            account=account,
            orders=[buy_order, sell_order],
            total_buy_amount=Decimal("1000.00"),
            total_sell_amount=Decimal("500.00"),
            net_cash_impact=Decimal("-500.00"),
        )

        assert len(plan.orders) == 2
        assert plan.total_buy_amount == Decimal("1000.00")
        assert plan.total_sell_amount == Decimal("500.00")
        assert plan.net_cash_impact == Decimal("-500.00")

    def test_buy_orders_property(self):
        """Test buy_orders property filters correctly."""
        account = Mock()
        security = Mock()
        asset_class = Mock()

        buy_order = RebalancingOrder(
            security=security,
            action="BUY",
            shares=10,
            estimated_amount=Decimal("1000.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )
        sell_order = RebalancingOrder(
            security=security,
            action="SELL",
            shares=5,
            estimated_amount=Decimal("500.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )

        plan = RebalancingPlan(
            account=account,
            orders=[buy_order, sell_order],
        )

        assert len(plan.buy_orders) == 1
        assert plan.buy_orders[0].action == "BUY"

    def test_sell_orders_property(self):
        """Test sell_orders property filters correctly."""
        account = Mock()
        security = Mock()
        asset_class = Mock()

        buy_order = RebalancingOrder(
            security=security,
            action="BUY",
            shares=10,
            estimated_amount=Decimal("1000.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )
        sell_order = RebalancingOrder(
            security=security,
            action="SELL",
            shares=5,
            estimated_amount=Decimal("500.00"),
            price_per_share=Decimal("100.00"),
            asset_class=asset_class,
        )

        plan = RebalancingPlan(
            account=account,
            orders=[buy_order, sell_order],
        )

        assert len(plan.sell_orders) == 1
        assert plan.sell_orders[0].action == "SELL"

    def test_max_drift_improvement(self):
        """Test max_drift_improvement calculation."""
        account = Mock()
        asset_class1 = Mock()
        asset_class2 = Mock()

        plan = RebalancingPlan(
            account=account,
            pre_drift={asset_class1: Decimal("5.0"), asset_class2: Decimal("-3.0")},
            post_drift={asset_class1: Decimal("1.0"), asset_class2: Decimal("-0.5")},
        )

        # Pre max: 5.0, Post max: 1.0, Improvement: 4.0
        assert plan.max_drift_improvement == Decimal("4.0")

    def test_max_drift_improvement_empty_drift(self):
        """Test max_drift_improvement with empty drift dicts."""
        account = Mock()

        plan = RebalancingPlan(account=account)

        assert plan.max_drift_improvement == Decimal("0")

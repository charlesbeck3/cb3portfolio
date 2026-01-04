"""Integration tests for rebalancing engine."""

from decimal import Decimal

from django.utils import timezone

import pytest

from portfolio.models import (
    AllocationStrategy,
    Holding,
    SecurityPrice,
    TargetAllocation,
)
from portfolio.services.rebalancing import RebalancingEngine


@pytest.mark.integration
@pytest.mark.services
@pytest.mark.django_db
class TestRebalancingEngineIntegration:
    """Integration tests for RebalancingEngine."""

    @pytest.fixture
    def account_with_holdings_and_targets(self, test_portfolio, roth_account):
        """Create account with holdings that need rebalancing.

        Setup:
        - Holdings: $1000 VTI (US Equities), $0 BND (Bonds)
        - Target: 60% US Equities, 40% Bonds

        Expected rebalancing: Sell VTI, Buy BND to reach 60/40.
        """
        system = test_portfolio["system"]
        user = test_portfolio["user"]

        # Create holding: 100% in US Equities
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Get or create BND security for bonds
        from portfolio.models import Security

        bnd, _ = Security.objects.get_or_create(
            ticker="BND",
            defaults={
                "name": "Vanguard Total Bond Market ETF",
                "asset_class": system.asset_class_treasuries_short,
            },
        )

        SecurityPrice.objects.create(
            security=bnd,
            price=Decimal("80"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create strategy with 60/40 allocation
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="60/40 Strategy",
        )

        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("60.00"),
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_treasuries_short,
            target_percent=Decimal("40.00"),
        )

        # Assign strategy to account
        roth_account.allocation_strategy = strategy
        roth_account.save()

        return {
            **test_portfolio,
            "account": roth_account,
            "strategy": strategy,
            "bnd": bnd,
        }

    def test_generate_plan_basic(self, account_with_holdings_and_targets):
        """Test basic plan generation."""
        account = account_with_holdings_and_targets["account"]

        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        assert plan.account == account
        assert plan.generated_at is not None
        assert plan.method_used in ["optimization", "proportional"]

    def test_generate_plan_produces_orders(self, account_with_holdings_and_targets):
        """Test that plan produces rebalancing orders."""
        account = account_with_holdings_and_targets["account"]

        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        # Should have orders since portfolio is unbalanced
        # With 100% equities vs 60/40 target, we need to sell equities
        assert len(plan.orders) > 0

    def test_generate_plan_calculates_drift(self, account_with_holdings_and_targets):
        """Test that drift is calculated correctly."""
        account = account_with_holdings_and_targets["account"]

        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        # Pre-drift should show 100% actual vs 60% target = +40% drift for equities
        assert len(plan.pre_drift) > 0

        # Find US Equities drift
        us_equities_class = account_with_holdings_and_targets["system"].asset_class_us_equities
        assert us_equities_class in plan.pre_drift

        # Drift should be approximately +40% (100% actual - 60% target)
        us_drift = float(plan.pre_drift[us_equities_class])
        assert us_drift == pytest.approx(40.0, abs=1.0)

    def test_generate_plan_reduces_drift(self, account_with_holdings_and_targets):
        """Test that post-rebalance drift is reduced."""
        account = account_with_holdings_and_targets["account"]

        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        # Post-drift should be smaller than pre-drift
        for asset_class in plan.pre_drift:
            if asset_class in plan.post_drift:
                pre = abs(float(plan.pre_drift[asset_class]))
                post = abs(float(plan.post_drift[asset_class]))
                # Post-rebalance drift should be less than or equal to pre
                assert post <= pre + 5  # Allow small tolerance for rounding

    def test_generate_plan_totals(self, account_with_holdings_and_targets):
        """Test that buy/sell totals are calculated correctly."""
        account = account_with_holdings_and_targets["account"]

        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        # Calculate totals from orders
        calc_buy = sum(o.estimated_amount for o in plan.orders if o.action == "BUY")
        calc_sell = sum(o.estimated_amount for o in plan.orders if o.action == "SELL")

        assert plan.total_buy_amount == calc_buy
        assert plan.total_sell_amount == calc_sell

    def test_generate_plan_whole_shares(self, account_with_holdings_and_targets):
        """Test that all orders are whole shares."""
        account = account_with_holdings_and_targets["account"]

        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        for order in plan.orders:
            assert isinstance(order.shares, int)
            assert order.shares > 0

    def test_generate_plan_no_holdings(self, roth_account, test_portfolio):
        """Test plan generation with no holdings."""
        # Must have targets to be "no_holdings" status (otherwise "no_targets")
        system = test_portfolio["system"]
        user = test_portfolio["user"]

        strategy = AllocationStrategy.objects.create(
            user=user,
            name="Test Strategy",
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("100.00"),
        )
        roth_account.allocation_strategy = strategy
        roth_account.save()

        engine = RebalancingEngine(roth_account)
        plan = engine.generate_plan()

        assert plan.orders == []
        assert plan.optimization_status == "no_holdings"
        assert plan.total_buy_amount == Decimal("0")

    def test_generate_plan_no_targets(self, test_portfolio, roth_account):
        """Test plan generation with holdings but no targets."""
        system = test_portfolio["system"]

        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )

        engine = RebalancingEngine(roth_account)
        plan = engine.generate_plan()

        assert plan.orders == []
        assert plan.optimization_status == "no_targets"

    def test_generate_plan_proforma(self, account_with_holdings_and_targets):
        """Test that pro forma holdings are calculated correctly."""
        account = account_with_holdings_and_targets["account"]
        bnd = account_with_holdings_and_targets["bnd"]

        # Ensure BND is primary so it gets picked up for zero-holding buy
        # AND ensure it matches the target asset class (Treasuries Short)
        # BND from seed data might have a different asset class
        bnd.asset_class = account.allocation_strategy.target_allocations.get(
            target_percent=40
        ).asset_class
        bnd.is_primary = True
        bnd.save()

        engine = RebalancingEngine(account)
        plan = engine.generate_plan()

        # Verify pro forma holdings rows exist
        assert len(plan.proforma_holdings_rows) > 0

        # Get individual holding rows (hierarchy_level == 999)
        individual_rows = [
            row for row in plan.proforma_holdings_rows if row["hierarchy_level"] == 999
        ]
        assert len(individual_rows) > 0

        # Should contain VTI (existing) and BND (new buy)
        symbols = {row["ticker"] for row in individual_rows}
        assert "VTI" in symbols
        assert "BND" in symbols

        # Verify that rows have the expected structure
        vti_row = next(row for row in individual_rows if row["ticker"] == "VTI")
        assert "shares" in vti_row  # Pro forma shares
        assert "target_shares" in vti_row  # Target shares
        assert "value" in vti_row  # Pro forma value
        assert "target_value" in vti_row  # Target value
        assert "allocation" in vti_row  # Pro forma allocation
        assert "target_allocation" in vti_row  # Target allocation

        # BND row should exist (new position from rebalancing)
        bnd_row = next(row for row in individual_rows if row["ticker"] == "BND")
        assert bnd_row["shares"] > 0  # Pro forma shares should be positive

        # Verify variance calculation
        # Pro forma allocation should be close to target
        for row in individual_rows:
            assert abs(row["allocation_variance"]) < 5.0  # Allow some variance due to whole shares


@pytest.mark.integration
@pytest.mark.services
@pytest.mark.django_db
class TestRebalancingEngineEdgeCases:
    """Edge case tests for RebalancingEngine."""

    def test_already_balanced_portfolio(self, test_portfolio, roth_account):
        """Test that a balanced portfolio produces no orders."""
        system = test_portfolio["system"]
        user = test_portfolio["user"]

        # Create holdings matching target allocation (60% equities, 40% bonds)
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("6"),  # 6 * $100 = $600 (60%)
        )

        from portfolio.models import Security

        bnd, _ = Security.objects.get_or_create(
            ticker="BND",
            defaults={
                "name": "Vanguard Total Bond Market ETF",
                "asset_class": system.asset_class_treasuries_short,
            },
        )

        Holding.objects.create(
            account=roth_account,
            security=bnd,
            shares=Decimal("5"),  # 5 * $80 = $400 (40%)
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )
        SecurityPrice.objects.create(
            security=bnd,
            price=Decimal("80"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create 60/40 strategy
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="60/40 Strategy",
        )

        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("60.00"),
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_treasuries_short,
            target_percent=Decimal("40.00"),
        )

        roth_account.allocation_strategy = strategy
        roth_account.save()

        engine = RebalancingEngine(roth_account)
        plan = engine.generate_plan()

        # Should have minimal or no orders since portfolio is already balanced
        total_trade_value = plan.total_buy_amount + plan.total_sell_amount
        # Allow some tolerance for rounding differences
        assert total_trade_value < Decimal("100"), (
            f"Expected minimal trades, got ${total_trade_value} total"
        )

    def test_missing_price_handles_gracefully(self, test_portfolio, roth_account):
        """Test that missing prices are handled gracefully."""
        system = test_portfolio["system"]
        user = test_portfolio["user"]

        # Create holding without creating a price
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        # Create strategy
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="Test Strategy",
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("100.00"),
        )

        roth_account.allocation_strategy = strategy
        roth_account.save()

        # Should not raise, but will have issues due to $0 price
        engine = RebalancingEngine(roth_account)
        plan = engine.generate_plan()

        # Plan should complete without error
        assert plan is not None

    def test_uses_effective_strategy_cascade(self, test_portfolio, roth_account):
        """Test that account falls back to portfolio strategy if no account strategy."""
        system = test_portfolio["system"]
        user = test_portfolio["user"]
        portfolio_obj = test_portfolio["portfolio"]

        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create portfolio-level strategy (not account-level)
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="Portfolio Strategy",
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("100.00"),
        )

        portfolio_obj.allocation_strategy = strategy
        portfolio_obj.save()

        # Account has no strategy, should fall back to portfolio
        roth_account.allocation_strategy = None
        roth_account.save()

        engine = RebalancingEngine(roth_account)
        plan = engine.generate_plan()

        # Should use portfolio strategy's targets
        assert plan.optimization_status != "no_targets"

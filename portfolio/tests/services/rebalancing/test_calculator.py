"""Unit tests for RebalancingCalculator."""

from decimal import Decimal

import pytest

from portfolio.models import Holding, Security
from portfolio.services.rebalancing.calculator import RebalancingCalculator


@pytest.mark.unit
@pytest.mark.services
@pytest.mark.django_db
class TestRebalancingCalculator:
    """Unit tests for RebalancingCalculator."""

    def test_asset_class_with_zero_holdings(
        self, roth_account, base_system_data, international_stocks
    ):
        """Test rebalancing when target includes asset class with no current holdings."""
        system = base_system_data

        # Create holdings: only US stocks and bonds
        # VTI - US Equities
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("100"),
        )

        # BND - Bond Market
        Holding.objects.create(
            account=roth_account,
            security=system.bnd,
            shares=Decimal("50"),
        )

        # Ensure VXUS is primary for International
        system.vxus.is_primary = True
        system.vxus.save()

        # Prices
        prices = {
            system.vti: Decimal("200.00"),  # $20,000
            system.bnd: Decimal("200.00"),  # $10,000
            system.vxus: Decimal("100.00"),  # For buying
        }
        # Total: $30,000 (67% US stocks, 33% bonds, 0% international)

        # Targets: 50% US, 30% international, 20% bonds
        targets = {
            system.asset_class_us_equities: Decimal("50.0"),
            international_stocks: Decimal("30.0"),
            system.asset_class_treasuries_short: Decimal("20.0"),
        }

        # Calculate
        calc = RebalancingCalculator(roth_account)
        orders, status, method = calc.calculate_orders(
            holdings=list(roth_account.holdings.all()),
            prices=prices,
            target_allocations=targets,
        )

        # Should have orders for all three asset classes
        symbols_traded = {o.security.ticker for o in orders}

        # Should include VXUS (buy international)
        assert system.vxus.ticker in symbols_traded

        # Should have buy order for international stocks
        vxus_orders = [o for o in orders if o.security == system.vxus]
        assert len(vxus_orders) > 0
        assert all(o.action == "BUY" for o in vxus_orders)

    def test_uses_primary_security(self, roth_account, base_system_data):
        """Test that primary security is chosen for zero-holding asset class."""
        system = base_system_data

        # Setup: Account with only Cash
        # Create Cash holding $10,000
        Holding.objects.create(
            account=roth_account,
            security=system.cash,
            shares=Decimal("10000"),
        )

        # Mark VTI as primary for US Equities
        system.vti.is_primary = True
        system.vti.save()

        # Create another US Equity security that is NOT primary
        other_stock = Security.objects.create(
            ticker="OTHER",
            name="Other Stock",
            asset_class=system.asset_class_us_equities,
            is_primary=False,
        )

        prices = {
            system.cash: Decimal("1.00"),
            system.vti: Decimal("200.00"),
            other_stock: Decimal("50.00"),
        }

        # Target: 100% US Equities
        targets = {
            system.asset_class_us_equities: Decimal("100.0"),
        }

        calc = RebalancingCalculator(roth_account)
        orders, _, _ = calc.calculate_orders(
            holdings=list(roth_account.holdings.all()),
            prices=prices,
            target_allocations=targets,
        )

        # Should buy VTI (primary), not OTHER
        traded_tickers = {o.security.ticker for o in orders}
        assert "VTI" in traded_tickers
        assert "OTHER" not in traded_tickers

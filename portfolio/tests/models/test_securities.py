from decimal import Decimal
from typing import Any

import pytest

from portfolio.models import AssetClass, Holding, Security


@pytest.mark.models
@pytest.mark.integration
def test_create_security(base_system_data: Any) -> None:
    """Test creating a security."""
    system = base_system_data
    asset_class = AssetClass.objects.create(
        name="US Stocks Sec",
        category=system.cat_us_eq,
    )
    security = Security.objects.create(
        ticker="VTI_SEC", asset_class=asset_class, name="Vanguard Stock"
    )
    assert security.ticker == "VTI_SEC"
    assert str(security) == "VTI_SEC - Vanguard Stock"


@pytest.mark.models
@pytest.mark.integration
class TestHolding:
    def test_create_holding(self, simple_holdings: dict[str, Any]) -> None:
        """Test creating a holding."""
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        # Create a new holding
        holding = Holding.objects.create(
            account=account,
            security=system.vxus,  # Use different security
            shares=Decimal("10.5000"),
            current_price=Decimal("210.00"),
        )
        assert holding.shares == Decimal("10.5000")
        assert str(holding) == f"VXUS in {account.name} (10.5000 shares)"

    def test_market_value_with_price(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]
        holding = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )
        assert holding.market_value == Decimal("1000")

    def test_market_value_without_price(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]
        holding = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("10"),
            current_price=None,
        )
        assert holding.market_value == Decimal("0.00")

    def test_has_price_property(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        holding_with_price = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("1"),
            current_price=Decimal("50"),
        )
        assert holding_with_price.has_price

        holding_without_price = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("1"),
            current_price=None,
        )
        assert not holding_without_price.has_price

    def test_update_price(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        holding = Holding.objects.create(
            account=account,
            security=system.vxus,
            shares=Decimal("5"),
            current_price=Decimal("10"),
        )
        holding.update_price(Decimal("20"))
        holding.refresh_from_db()
        assert holding.current_price == Decimal("20")

    def test_calculate_target_value_and_variance(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        holding = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )

        account_total = Decimal("10000")
        target_pct = Decimal("25")
        target_value = holding.calculate_target_value(account_total, target_pct)
        assert target_value == Decimal("2500")

        # Current value: 1000, Target: 2500 -> variance: -1500 (underweight)
        variance = holding.calculate_variance(target_value)
        assert variance == Decimal("1000") - Decimal("2500")

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.urls import reverse

import pytest

from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    Holding,
    TargetAllocation,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine

User = get_user_model()


@pytest.mark.edge_cases
@pytest.mark.integration
def test_empty_portfolio_allocations(test_portfolio: dict[str, Any]) -> None:
    """Empty portfolio should return zeros, not crash."""
    user = test_portfolio["user"]
    engine = AllocationCalculationEngine()
    df = engine.build_presentation_dataframe(user=user)

    # If empty, df should be empty
    assert df.empty

    # Check aggregation on empty df
    aggregated = engine.aggregate_presentation_levels(df)
    assert aggregated["grand_total"].empty


@pytest.mark.edge_cases
@pytest.mark.integration
def test_empty_portfolio_dashboard(
    client: Any, test_portfolio: dict[str, Any], zero_prices: Any
) -> None:
    """Dashboard should render cleanly with no holdings."""
    user = test_portfolio["user"]
    client.force_login(user)

    # zero_prices fixture mocks empty prices
    response = client.get(reverse("portfolio:dashboard"))

    assert response.status_code == 200
    assert "Dashboard" in response.content.decode()


@pytest.mark.edge_cases
@pytest.mark.integration
def test_allocations_sum_to_99_99(test_portfolio: dict[str, Any]) -> None:
    """Allocations summing to 99.99% should be handled by cash remainder."""
    user = test_portfolio["user"]
    system = test_portfolio["system"]

    strategy = AllocationStrategy.objects.create(user=user, name="99.99 Strategy")
    # Asset classes
    ac_us = system.asset_class_us_equities
    TargetAllocation.objects.create(
        strategy=strategy, asset_class=ac_us, target_percent=Decimal("99.99")
    )

    # Cash should be 0.01%
    # AllocationStrategy model now has logic to handle cash remainder if used via save_allocations
    strategy.save_allocations({ac_us.id: Decimal("99.99")})

    cash_alloc = strategy.target_allocations.get(asset_class=system.asset_class_cash)
    assert cash_alloc.target_percent == Decimal("0.01")


@pytest.mark.edge_cases
@pytest.mark.integration
def test_billion_dollar_portfolio(test_portfolio: dict[str, Any]) -> None:
    """Calculations should work for $1B+ portfolios."""
    user = test_portfolio["user"]
    system = test_portfolio["system"]
    portfolio = test_portfolio["portfolio"]

    account = Account.objects.create(
        user=user,
        name="Whale Account",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    # 10,000,000 shares @ $100 = $1B
    Holding.objects.create(
        account=account,
        security=system.vti,
        shares=Decimal("10000000"),
        current_price=Decimal("100"),
    )

    engine = AllocationCalculationEngine()
    df = engine.build_presentation_dataframe(user=user)
    aggregated = engine.aggregate_presentation_levels(df)

    grand_total = aggregated["grand_total"]
    # Columns in grand_total include 'portfolio_actual'
    assert grand_total["portfolio_actual"].iloc[0] == 1000000000.0


@pytest.mark.edge_cases
@pytest.mark.integration
def test_account_with_no_holdings(test_portfolio: dict[str, Any]) -> None:
    """Account exists but has zero holdings - should appear with $0."""
    user = test_portfolio["user"]
    system = test_portfolio["system"]
    portfolio = test_portfolio["portfolio"]

    account = Account.objects.create(
        user=user,
        name="Empty Account",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )
    assert account.total_value() == Decimal("0.00")


@pytest.mark.edge_cases
@pytest.mark.integration
def test_partial_allocations_auto_fill_cash(test_portfolio: dict[str, Any]) -> None:
    """Allocations that don't sum to 100% - auto-allocate to cash."""
    user = test_portfolio["user"]
    system = test_portfolio["system"]

    strategy = AllocationStrategy.objects.create(user=user, name="Partial Strategy")

    # 80% to US Equities
    strategy.save_allocations({system.asset_class_us_equities.id: Decimal("80.00")})

    # Should have created a cash allocation of 20%
    cash_alloc = strategy.target_allocations.get(asset_class=system.asset_class_cash)
    assert cash_alloc.target_percent == Decimal("20.00")


@pytest.mark.edge_cases
@pytest.mark.integration
def test_strategy_inheritance(test_portfolio: dict[str, Any]) -> None:
    """Type-level allocation applies to all accounts of that type."""
    user = test_portfolio["user"]
    system = test_portfolio["system"]
    portfolio = test_portfolio["portfolio"]

    # Create two taxable accounts
    acc1 = Account.objects.create(
        user=user,
        name="Taxable 1",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )
    acc2 = Account.objects.create(
        user=user,
        name="Taxable 2",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    # Create strategy
    strategy = AllocationStrategy.objects.create(user=user, name="Taxable Strategy")

    # Assign to TYPE
    AccountTypeStrategyAssignment.objects.create(
        user=user, account_type=system.type_taxable, allocation_strategy=strategy
    )

    # Both accounts should inherit the strategy
    assert acc1.get_effective_allocation_strategy() == strategy
    assert acc2.get_effective_allocation_strategy() == strategy


@pytest.mark.edge_cases
@pytest.mark.integration
def test_zero_price_valuation(test_portfolio: dict[str, Any]) -> None:
    """Holdings with missing or zero prices."""
    user = test_portfolio["user"]
    system = test_portfolio["system"]
    portfolio = test_portfolio["portfolio"]

    account = Account.objects.create(
        user=user,
        name="Acc",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    # Holding with 0 price explicitly
    h1 = Holding.objects.create(
        account=account, security=system.vti, shares=100, current_price=Decimal("0.00")
    )
    assert h1.market_value == Decimal("0.00")

    # Holding with noprice
    h2 = Holding.objects.create(
        account=account, security=system.vxus, shares=100, current_price=None
    )
    assert h2.market_value == Decimal("0.00")

"""
Fixtures for golden reference tests.

Provides complete real-world portfolio setup for accuracy testing.
"""

from decimal import Decimal
from typing import Any

from django.utils import timezone

import pytest

from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    Holding,
    Portfolio,
    SecurityPrice,
)


@pytest.fixture
def golden_reference_portfolio(test_user: Any, base_system_data: Any) -> dict[str, Any]:
    """
    Complete real-world portfolio for golden reference testing.

    Portfolio structure:
    - ML Brokerage (Taxable): $200k
    - CB IRA (Traditional): $150k
    - CB Roth (Roth): $100k

    Total: $450k

    Strategies:
    - Taxable Default: 30% US Eq, 40% Intl, 30% Bonds
    - Tax Deferred: 25% US Eq, 25% Intl, 50% Bonds
    - Tax Advantaged: 50% US Eq, 30% Intl, 20% Bonds

    Replaces: PortfolioTestMixin setup in test_golden_reference.py
    """
    system = base_system_data
    portfolio = Portfolio.objects.create(user=test_user, name="Golden Reference Portfolio")

    # Create strategies
    strategy_taxable = AllocationStrategy.objects.create(user=test_user, name="Taxable Default")
    strategy_taxable.save_allocations(
        {
            system.asset_class_us_equities.id: Decimal("30.00"),
            system.asset_class_intl_developed.id: Decimal("40.00"),
            system.asset_class_treasuries_short.id: Decimal("30.00"),
        }
    )

    strategy_tax_deferred = AllocationStrategy.objects.create(user=test_user, name="Tax Deferred")
    strategy_tax_deferred.save_allocations(
        {
            system.asset_class_us_equities.id: Decimal("25.00"),
            system.asset_class_intl_developed.id: Decimal("25.00"),
            system.asset_class_treasuries_short.id: Decimal("50.00"),
        }
    )

    strategy_tax_advantaged = AllocationStrategy.objects.create(
        user=test_user, name="Tax Advantaged"
    )
    strategy_tax_advantaged.save_allocations(
        {
            system.asset_class_us_equities.id: Decimal("50.00"),
            system.asset_class_intl_developed.id: Decimal("30.00"),
            system.asset_class_treasuries_short.id: Decimal("20.00"),
        }
    )

    # Assign strategies to account types
    AccountTypeStrategyAssignment.objects.create(
        user=test_user,
        account_type=system.type_taxable,
        allocation_strategy=strategy_taxable,
    )
    AccountTypeStrategyAssignment.objects.create(
        user=test_user,
        account_type=system.type_trad,
        allocation_strategy=strategy_tax_deferred,
    )
    AccountTypeStrategyAssignment.objects.create(
        user=test_user,
        account_type=system.type_roth,
        allocation_strategy=strategy_tax_advantaged,
    )

    # Create accounts
    acc_ml_brokerage = Account.objects.create(
        user=test_user,
        name="ML Brokerage",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    acc_cb_ira = Account.objects.create(
        user=test_user,
        name="CB IRA",
        portfolio=portfolio,
        account_type=system.type_trad,
        institution=system.institution,
    )

    acc_cb_roth = Account.objects.create(
        user=test_user,
        name="CB Roth",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )

    # Create holdings
    # ML Brokerage: $200k total (2000 shares @ $100 each)
    Holding.objects.create(
        account=acc_ml_brokerage,
        security=system.vti,
        shares=Decimal("2000"),
    )

    # CB IRA: $150k total (1500 shares @ $100 each)
    Holding.objects.create(
        account=acc_cb_ira,
        security=system.vxus,
        shares=Decimal("1500"),
    )

    # CB Roth: $100k total (1000 shares @ $100 each)
    Holding.objects.create(
        account=acc_cb_roth,
        security=system.vti,
        shares=Decimal("1000"),
    )

    # Create prices
    now = timezone.now()
    SecurityPrice.objects.create(
        security=system.vti, price=Decimal("100.00"), price_datetime=now, source="manual"
    )
    SecurityPrice.objects.create(
        security=system.vxus, price=Decimal("100.00"), price_datetime=now, source="manual"
    )

    return {
        "user": test_user,
        "portfolio": portfolio,
        "system": system,
        "accounts": {
            "ml_brokerage": acc_ml_brokerage,
            "cb_ira": acc_cb_ira,
            "cb_roth": acc_cb_roth,
        },
        "strategies": {
            "taxable": strategy_taxable,
            "tax_deferred": strategy_tax_deferred,
            "tax_advantaged": strategy_tax_advantaged,
        },
    }

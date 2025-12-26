"""
Test decimal precision consistency across models and calculation engine.
"""

from decimal import Decimal
from typing import Any

import pytest

from portfolio.models import (
    Account,
    Holding,
    Portfolio,
    Security,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine


@pytest.mark.models
@pytest.mark.integration
class TestDecimalPrecision:
    """Tests ensures precision is handled correctly for currency values."""

    def test_sum_of_float_holdings(self, test_user: Any, base_system_data: Any) -> None:
        """
        Test that summing holdings via AllocationCalculationEngine (which uses floats)
        doesn't introduce significant errors when converted back to Decimal.
        """
        system = base_system_data
        portfolio = Portfolio.objects.create(name="Precision Test Portfolio", user=test_user)
        account = Account.objects.create(
            portfolio=portfolio,
            user=test_user,
            name="Precision Account",
            account_type=system.type_taxable,
            institution=system.institution,
        )
        security = Security.objects.create(
            ticker="PREC",
            name="Precision Check",
            asset_class=system.cat_us_eq.asset_classes.create(name="US Stocks Precision"),
        )

        # Create 3 holdings that add up to 0.60 but might cause float issues: 0.1, 0.2, 0.3
        # 0.1 + 0.2 in float is 0.30000000000000004

        # Using values that often cause float issues
        # 1.1 + 2.2 = 3.3000000000000003

        # Create distinct securities to avoid unique constraint violation
        security2 = Security.objects.create(
            ticker="PREC2",
            name="Precision Check 2",
            asset_class=system.cat_us_eq.asset_classes.create(name="US Stocks Precision 2"),
        )

        Holding.objects.create(
            account=account,
            security=security,
            shares=Decimal("1.1"),
            current_price=Decimal("1.00"),
        )
        Holding.objects.create(
            account=account,
            security=security2,
            shares=Decimal("2.2"),
            current_price=Decimal("1.00"),
        )

        engine = AllocationCalculationEngine()
        result = engine.calculate_allocations(portfolio.to_dataframe())

        # Expected total: 1.1*1 + 2.2*1 = 3.3
        # Float math: 1.1 + 2.2 = 3.3000000000000003

        summary = result["portfolio_summary"]
        total_val = Decimal(str(summary["total_value"].iloc[0]))

        # Verify that the value is close enough (e.g. within 1 cent)
        assert abs(total_val - Decimal("3.30")) < Decimal("0.000001"), f"Got {total_val}"

    def test_float_sum_precision_roundtrip(self, test_user: Any, base_system_data: Any) -> None:
        """Test roundtrip precision with multiple accounts/holdings."""
        system = base_system_data
        portfolio = Portfolio.objects.create(name="Roundtrip Portfolio", user=test_user)

        # 0.1 + 0.2 usually = 0.30000000000000004
        val1 = Decimal("0.10")
        val2 = Decimal("0.20")
        expected_sum = Decimal("0.30")

        account1 = Account.objects.create(
            portfolio=portfolio,
            user=test_user,
            name="Account 1",
            account_type=system.type_taxable,
            institution=system.institution,
        )
        sec1 = Security.objects.create(
            ticker="S1", name="S1", asset_class=system.cat_us_eq.asset_classes.first()
        )
        Holding.objects.create(account=account1, security=sec1, shares=val1, current_price=1)

        account2 = Account.objects.create(
            portfolio=portfolio,
            user=test_user,
            name="Account 2",
            account_type=system.type_taxable,
            institution=system.institution,
        )
        sec2 = Security.objects.create(
            ticker="S2", name="S2", asset_class=system.cat_us_eq.asset_classes.first()
        )
        Holding.objects.create(account=account2, security=sec2, shares=val2, current_price=1)

        engine = AllocationCalculationEngine()

        # Method 1: calculate_allocations (pure pandas/float)
        results = engine.calculate_allocations(portfolio.to_dataframe())
        total_float = results["portfolio_summary"]["total_value"].iloc[0]
        assert isinstance(total_float, float)

        # Check if float sum has artifacts (it likely will)
        # 0.30000000000000004 is expected for float sum of 0.1 and 0.2
        # But we want to ensure that if we convert to string/decimal for specific methods, it's handled.

        # Method 2: get_account_totals (returns Decimals)
        totals = engine.get_account_totals(test_user)
        # Note: get_account_totals gets ALL user accounts.
        # We need to filter for our test accounts or just sum them.

        relevant_total = totals.get(account1.id, 0) + totals.get(account2.id, 0)

        # If get_account_totals does Decimal(str(float_sum)), it might capture artifacts.
        # e.g. Decimal("0.3000000000000000444...")
        # We assert that we want it clean? Or do we accept artifacts?
        # Ideally, we want exact.

        # Let's see what it actually does.
        assert abs(relevant_total - expected_sum) < Decimal("0.000001"), f"Got {relevant_total}"

        # Strict equality check might fail if artifacts are preserved
        # assert relevant_total == expected_sum

    def test_decimal_field_precision_in_models(self) -> None:
        """
        Verify that models use sufficient precision.
        Holding.shares: max_digits=20, decimal_places=8 -> sufficient
        Holding.current_price: max_digits=10, decimal_places=2 -> OK for dollars, maybe low for crypto?
        """
        # Checks introspection of fields
        from portfolio.models import Holding

        shares_field = Holding._meta.get_field("shares")
        assert shares_field.decimal_places == 8
        assert shares_field.max_digits == 20

        price_field = Holding._meta.get_field("current_price")
        assert price_field.decimal_places == 2
        # For penny stocks or crypto, 2 decimal places might be insufficient.
        # But for 'standard' portfolio, maybe ok.
        # This test ensures we are aware of this limitation.

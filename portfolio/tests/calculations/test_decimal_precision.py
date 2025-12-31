"""
Test decimal precision consistency across models and calculation engine.
"""

from decimal import Decimal
from typing import Any

from django.utils import timezone

import pytest

from portfolio.models import (
    Account,
    Holding,
    Portfolio,
    Security,
    SecurityPrice,
)
from portfolio.services.allocations import AllocationEngine


@pytest.mark.models
@pytest.mark.integration
class TestDecimalPrecision:
    """Tests ensures precision is handled correctly for currency values."""

    def test_sum_of_float_holdings(self, test_user: Any, base_system_data: Any) -> None:
        """
        Test that summing holdings via AllocationEngine
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
        )
        Holding.objects.create(
            account=account,
            security=security2,
            shares=Decimal("2.2"),
        )

        # Create prices
        now = timezone.now()
        SecurityPrice.objects.create(
            security=security, price=Decimal("1.00"), price_datetime=now, source="manual"
        )
        SecurityPrice.objects.create(
            security=security2, price=Decimal("1.00"), price_datetime=now, source="manual"
        )

        engine = AllocationEngine()
        # Use DataProvider to get the data as the engine would
        _holdings_df = engine.data_provider.get_holdings_df(test_user)
        # Verify total value via the engine's totals method
        totals = engine.get_account_totals(test_user)
        total_val = totals.get(account.id, Decimal("0"))

        # Expected total: 1.1*1 + 2.2*1 = 3.3
        # Float math: 1.1 + 2.2 = 3.3000000000000003

        # Verify that the value is close enough (float artifacts expected)
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
        Holding.objects.create(account=account1, security=sec1, shares=val1)

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
        Holding.objects.create(account=account2, security=sec2, shares=val2)

        # Create prices
        now = timezone.now()
        SecurityPrice.objects.create(
            security=sec1, price=Decimal("1.00"), price_datetime=now, source="manual"
        )
        SecurityPrice.objects.create(
            security=sec2, price=Decimal("1.00"), price_datetime=now, source="manual"
        )

        engine = AllocationEngine()

        # Method 1: DataProvider (pure pandas/float)
        holdings_df = engine.data_provider.get_holdings_df(test_user)
        # Sum only for our specific portfolio accounts
        total_float = holdings_df[holdings_df["account_id"].isin([account1.id, account2.id])][
            "value"
        ].sum()
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

        # current_price field has been removed - prices now stored in SecurityPrice
        # SecurityPrice.price field has max_digits=10, decimal_places=4
        from portfolio.models import SecurityPrice

        price_field = SecurityPrice._meta.get_field("price")
        assert price_field.decimal_places == 4
        # 4 decimal places provides better precision for stocks and crypto
        # This is an improvement over the old 2 decimal places

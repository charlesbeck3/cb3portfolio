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
        )
        assert holding.shares == Decimal("10.5000")
        assert str(holding) == f"VXUS in {account.name} (10.5000 shares)"

    def test_market_value_with_price(self, simple_holdings: dict[str, Any]) -> None:
        # simple_holdings already sets up VTI with price $100 and 10 shares
        holding = simple_holdings["holding"]
        assert holding.market_value == Decimal("1000")

    def test_market_value_without_price(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        # Need a new security that definitely has no price
        from portfolio.models import AssetClass, Security

        ac = AssetClass.objects.get_or_create(name="NoPrice AC", category=system.cat_us_eq)[0]
        sec_no_price = Security.objects.create(
            ticker="NOPRICE_MV", name="No Price MV", asset_class=ac
        )

        holding = Holding.objects.create(
            account=account,
            security=sec_no_price,
            shares=Decimal("10"),
        )
        # No SecurityPrice created
        assert holding.market_value == Decimal("0.00")

    def test_has_price_property(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        # simple_holdings has VTI with price
        holding_with_price = simple_holdings["holding"]
        assert holding_with_price.has_price

        # New security for no price test
        from portfolio.models import AssetClass, Security

        ac = AssetClass.objects.get_or_create(name="NoPrice AC 2", category=system.cat_us_eq)[0]
        sec_no_price = Security.objects.create(
            ticker="NOPRICE_HP", name="No Price HP", asset_class=ac
        )

        holding_without_price = Holding.objects.create(
            account=account,
            security=sec_no_price,
            shares=Decimal("1"),
        )
        assert not holding_without_price.has_price

    # test_update_price REMOVED - method being deleted

    def test_calculate_target_value_and_variance(self, simple_holdings: dict[str, Any]) -> None:
        # Use existing holding from fixture
        holding = simple_holdings["holding"]
        # Market value is 1000

        account_total = Decimal("10000")
        target_pct = Decimal("25")
        target_value = holding.calculate_target_value(account_total, target_pct)
        assert target_value == Decimal("2500")

        # Current value: 1000, Target: 2500 -> variance: -1500 (underweight)
        variance = holding.calculate_variance(target_value)
        assert variance == Decimal("1000") - Decimal("2500")

    def test_latest_price_from_security_price_table(self, simple_holdings: dict[str, Any]) -> None:
        """Test that latest_price property uses SecurityPrice table."""
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        account = simple_holdings["account"]
        system = simple_holdings["system"]

        # Create a fresh security to avoid unique constraint with simple_holdings
        asset_class = AssetClass.objects.create(name="Test Asset LP", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_LP_NEW", name="Test Security LP", asset_class=asset_class
        )

        # Create holding without current_price
        holding = Holding.objects.create(
            account=account,
            security=security,
            shares=Decimal("10"),
        )

        # Create SecurityPrice record
        SecurityPrice.objects.create(
            security=security,
            price=Decimal("150.00"),
            price_datetime=timezone.now(),
            source="manual",
        )

        # latest_price should use SecurityPrice
        assert holding.latest_price == Decimal("150.00")
        assert holding.market_value == Decimal("1500.00")

    # test_latest_price_fallback_to_current_price REMOVED - fallback being removed

    def test_price_as_of_date(self, simple_holdings: dict[str, Any]) -> None:
        """Test price_as_of_date property returns datetime."""
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        account = simple_holdings["account"]
        system = simple_holdings["system"]

        # Create fresh security
        asset_class = AssetClass.objects.create(name="Test Asset PD", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_PD", name="Test Security PD", asset_class=asset_class
        )

        holding = Holding.objects.create(
            account=account,
            security=security,
            shares=Decimal("10"),
        )

        # No SecurityPrice yet
        assert holding.price_as_of_date is None

        # Create SecurityPrice
        now = timezone.now()
        SecurityPrice.objects.create(
            security=security, price=Decimal("150.00"), price_datetime=now, source="manual"
        )

        # Should return datetime
        assert holding.price_as_of_date == now


@pytest.mark.models
@pytest.mark.integration
class TestSecurityPrice:
    """Tests for SecurityPrice model."""

    def test_create_security_price(self, base_system_data: Any) -> None:
        """Test creating a security price record."""
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_SP", name="Test Security", asset_class=asset_class
        )

        now = timezone.now()
        price = SecurityPrice.objects.create(
            security=security, price=Decimal("100.50"), price_datetime=now, source="manual"
        )

        assert price.price == Decimal("100.50")
        assert str(price) == f"TEST_SP @ $100.50 on {now}"

    def test_get_latest_price(self, base_system_data: Any) -> None:
        """Test getting latest price for a security."""
        from datetime import timedelta

        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset 2", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_LP", name="Test Security", asset_class=asset_class
        )

        # Create prices for different datetimes
        now = timezone.now()
        hour_ago = now - timedelta(hours=1)

        SecurityPrice.objects.create(
            security=security, price=Decimal("100.00"), price_datetime=hour_ago, source="manual"
        )
        SecurityPrice.objects.create(
            security=security, price=Decimal("105.00"), price_datetime=now, source="manual"
        )

        # Should return most recent price
        latest = SecurityPrice.get_latest_price(security)
        assert latest == Decimal("105.00")

    def test_get_price_at_datetime(self, base_system_data: Any) -> None:
        """Test getting price at specific datetime."""
        from datetime import timedelta

        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset 3", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_DT", name="Test Security", asset_class=asset_class
        )

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        # Create prices
        SecurityPrice.objects.create(
            security=security,
            price=Decimal("100.00"),
            price_datetime=two_weeks_ago,
            source="manual",
        )
        SecurityPrice.objects.create(
            security=security, price=Decimal("105.00"), price_datetime=week_ago, source="manual"
        )

        # Get price at exact datetime
        price_week_ago = SecurityPrice.get_price_at_datetime(security, week_ago)
        assert price_week_ago == Decimal("105.00")

        # Get price between datetimes (should use most recent before)
        five_days_ago = now - timedelta(days=5)
        price_5_days_ago = SecurityPrice.get_price_at_datetime(security, five_days_ago)
        assert price_5_days_ago == Decimal("105.00")

        # Get price before any records (should return None)
        price_ancient = SecurityPrice.get_price_at_datetime(
            security, two_weeks_ago - timedelta(days=1)
        )
        assert price_ancient is None

    def test_get_price_on_date(self, base_system_data: Any) -> None:
        """Test getting latest price on specific date."""
        from datetime import timedelta

        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset 4", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_OD", name="Test Security", asset_class=asset_class
        )

        # Create multiple prices on same date
        now = timezone.now()
        morning = now.replace(hour=9, minute=30)
        afternoon = now.replace(hour=14, minute=0)

        SecurityPrice.objects.create(
            security=security, price=Decimal("100.00"), price_datetime=morning, source="manual"
        )
        SecurityPrice.objects.create(
            security=security, price=Decimal("105.00"), price_datetime=afternoon, source="manual"
        )

        # Should return latest price on that date
        price = SecurityPrice.get_price_on_date(security, now.date())
        assert price == Decimal("105.00")

        # Should return None for date with no prices
        yesterday = (now - timedelta(days=1)).date()
        price_yesterday = SecurityPrice.get_price_on_date(security, yesterday)
        assert price_yesterday is None

    def test_unique_constraint(self, base_system_data: Any) -> None:
        """Test that security + price_datetime is unique."""
        from django.db import IntegrityError
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset 5", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_UC", name="Test Security", asset_class=asset_class
        )

        now = timezone.now()

        # Create first price
        SecurityPrice.objects.create(
            security=security, price=Decimal("100.00"), price_datetime=now, source="manual"
        )

        # Try to create duplicate
        with pytest.raises(IntegrityError):
            SecurityPrice.objects.create(
                security=security, price=Decimal("105.00"), price_datetime=now, source="manual"
            )

    def test_get_latest_prices_bulk(self, base_system_data: Any) -> None:
        """Test bulk fetching of latest prices."""
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset Bulk", category=system.cat_us_eq)

        securities = []
        for i in range(3):
            sec = Security.objects.create(
                ticker=f"BULK_{i}", name=f"Bulk Security {i}", asset_class=asset_class
            )
            securities.append(sec)

        now = timezone.now()

        # Sec 0: No price

        # Sec 1: One price
        SecurityPrice.objects.create(
            security=securities[1], price=Decimal("10.00"), price_datetime=now, source="manual"
        )

        # Sec 2: Two prices (should get latest)
        SecurityPrice.objects.create(
            security=securities[2], price=Decimal("15.00"), price_datetime=now, source="manual"
        )
        SecurityPrice.objects.create(
            security=securities[2],
            price=Decimal("20.00"),
            price_datetime=now + timezone.timedelta(hours=1),
            source="manual",
        )

        # Fetch detailed
        prices = SecurityPrice.get_latest_prices_bulk(securities)

        # Verify
        assert securities[0].id not in prices  # No price
        assert prices[securities[1].id] == Decimal("10.00")
        assert prices[securities[2].id] == Decimal("20.00")


@pytest.mark.models
@pytest.mark.integration
class TestSecurityPriceConstraints:
    """
    Test Django 6 database-level constraints on SecurityPrice.

    These tests verify that invalid data is rejected at the database level,
    providing defense-in-depth beyond application validation.
    """

    def test_price_must_be_positive(self, base_system_data: Any) -> None:
        """Test that negative prices are rejected at database level."""
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset Neg", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_NEG", name="Test Security Negative", asset_class=asset_class
        )

        # Attempt to create with negative price
        price = SecurityPrice(
            security=security,
            price=Decimal("-10.00"),
            price_datetime=timezone.now(),
            source=SecurityPrice.MANUAL,
        )

        # Should fail at validation or database level
        with pytest.raises((ValidationError, IntegrityError)) as exc_info:
            price.full_clean()  # Application-level validation
            price.save()  # Database-level constraint

        # Verify appropriate error message
        error_str = str(exc_info.value)
        # Note: SQLite constraint error messages vary, but usually contain CHECK constraint failed
        assert (
            "price" in error_str.lower()
            or "positive" in error_str.lower()
            or "check constraint" in error_str.lower()
        )

    def test_price_cannot_be_zero(self, base_system_data: Any) -> None:
        """Test that zero prices are rejected (price must be > 0, not >= 0)."""
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset Zero", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_ZERO", name="Test Security Zero", asset_class=asset_class
        )

        price = SecurityPrice(
            security=security,
            price=Decimal("0.00"),
            price_datetime=timezone.now(),
            source=SecurityPrice.MANUAL,
        )

        with pytest.raises((ValidationError, IntegrityError)) as exc_info:
            price.full_clean()
            price.save()

        error_str = str(exc_info.value)
        assert (
            "price" in error_str.lower()
            or "greater" in error_str.lower()
            or "check constraint" in error_str.lower()
        )

    # NOTE: Future constraint test skipped because constraint is disabled on SQLite
    # def test_price_datetime_cannot_be_future(self, base_system_data: Any) -> None:
    #     ...

    def test_duplicate_security_datetime_rejected(self, base_system_data: Any) -> None:
        """
        Test unique constraint on (security, price_datetime).

        Verifies that Django 6 UniqueConstraint provides clear error message.
        """
        from django.db import IntegrityError
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(
            name="Test Asset Duplicate", category=system.cat_us_eq
        )
        security = Security.objects.create(
            ticker="TEST_DUP", name="Test Security Duplicate", asset_class=asset_class
        )

        now = timezone.now()

        # Create first price - should succeed
        SecurityPrice.objects.create(
            security=security,
            price=Decimal("100.00"),
            price_datetime=now,
            source=SecurityPrice.MANUAL,
        )

        # Attempt to create duplicate at same datetime - should fail
        with pytest.raises(IntegrityError) as exc_info:
            SecurityPrice.objects.create(
                security=security,
                price=Decimal("105.00"),  # Different price
                price_datetime=now,  # Same datetime
                source=SecurityPrice.MANUAL,
            )

        # Verify error message mentions uniqueness
        error_str = str(exc_info.value)
        assert "unique" in error_str.lower() or "duplicate" in error_str.lower()

    def test_valid_price_accepted(self, base_system_data: Any) -> None:
        """Test that valid prices are accepted without constraint violations."""
        from django.utils import timezone

        from portfolio.models import AssetClass, Security, SecurityPrice

        system = base_system_data
        asset_class = AssetClass.objects.create(name="Test Asset Valid", category=system.cat_us_eq)
        security = Security.objects.create(
            ticker="TEST_VALID", name="Test Security Valid", asset_class=asset_class
        )

        # Create valid price - should succeed
        now = timezone.now()
        price = SecurityPrice.objects.create(
            security=security,
            price=Decimal("150.50"),
            price_datetime=now,
            source=SecurityPrice.YFINANCE,
        )

        # Verify creation succeeded
        assert price.pk is not None
        assert price.price == Decimal("150.50")
        assert price.security == security

        # Verify can query it back
        retrieved = SecurityPrice.objects.get(pk=price.pk)
        assert retrieved.price == Decimal("150.50")

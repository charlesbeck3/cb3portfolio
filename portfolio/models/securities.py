from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from django.core.validators import MinValueValidator
from django.db import models

from portfolio.managers import HoldingManager

if TYPE_CHECKING:
    pass


class Security(models.Model):
    """Individual investment security (e.g., VTI, BND)."""

    ticker = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    asset_class = models.ForeignKey(
        "AssetClass", on_delete=models.PROTECT, related_name="securities"
    )

    class Meta:
        ordering = ["ticker"]
        verbose_name_plural = "Securities"

    def __str__(self) -> str:
        return f"{self.ticker} - {self.name}"

    @property
    def is_primary_for_asset_class(self) -> bool:
        """Check if this security is the primary for its asset class."""
        return (
            self.asset_class.primary_security_id is not None
            and self.asset_class.primary_security_id == self.id
        )


class SecurityPrice(models.Model):
    """
    Historical price data for securities.

    Centralizes price storage to eliminate duplication and provide
    price history for reproducible calculations.

    Design Notes:
    - One record per security per market timestamp
    - price_datetime: Actual market time from data provider (used for lookups)
    - fetched_at: When we retrieved the price (audit trail only)
    - Tracks price source (yfinance, manual, etc.)
    - Audit trail via fetched_at timestamp
    - Supports time-travel queries for historical analysis

    The distinction between price_datetime and fetched_at is important:
    - price_datetime: "When did the market report this price?" (e.g., 4:00 PM market close)
    - fetched_at: "When did we retrieve this data?" (e.g., 5:30 PM our fetch time)

    This allows us to see lag between market time and fetch time, useful for
    debugging and understanding data freshness.
    """

    security = models.ForeignKey(
        "Security",
        on_delete=models.CASCADE,
        related_name="prices",
        help_text="Security this price belongs to",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Price per share",
    )
    price_datetime = models.DateTimeField(
        db_index=True, help_text="Market timestamp from data provider (actual market time)"
    )
    fetched_at = models.DateTimeField(
        auto_now_add=True, help_text="When we fetched this price from data source (audit trail)"
    )
    source = models.CharField(
        max_length=20,
        choices=[
            ("yfinance", "Yahoo Finance"),
            ("manual", "Manual Entry"),
            ("calculated", "Calculated"),
        ],
        default="yfinance",
        help_text="Source of this price",
    )

    class Meta:
        unique_together = ["security", "price_datetime"]
        ordering = ["-price_datetime"]
        indexes = [
            models.Index(fields=["security", "-price_datetime"]),
            models.Index(fields=["price_datetime"]),  # For time range queries
        ]
        verbose_name = "Security Price"
        verbose_name_plural = "Security Prices"

    def __str__(self) -> str:
        return f"{self.security.ticker} @ ${self.price} on {self.price_datetime}"

    @classmethod
    def get_latest_price(cls, security: Security) -> Decimal | None:
        """
        Get most recent price for a security.

        Returns:
            Latest price as Decimal, or None if no prices exist
        """
        latest = cls.objects.filter(security=security).first()
        return latest.price if latest else None

    def is_stale(self, max_age: timedelta = timedelta(minutes=5)) -> bool:
        """
        Check if this price is stale and needs refreshing.

        Args:
            max_age: Maximum age before price is considered stale (default: 5 minutes)

        Returns:
            True if price is older than max_age, False otherwise
        """
        if not self.price_datetime:
            return True

        from django.utils import timezone

        age = timezone.now() - self.price_datetime
        return age > max_age

    @classmethod
    def get_stale_securities(
        cls, user: Any, max_age: timedelta = timedelta(minutes=5)
    ) -> models.QuerySet[Security]:
        """
        Get all securities owned by user that have stale prices.

        Args:
            user: User to check holdings for
            max_age: Maximum age before price is considered stale

        Returns:
            QuerySet of Security objects that need price updates
        """
        from django.utils import timezone

        cutoff_time = timezone.now() - max_age

        # Get all securities in user's holdings
        user_securities = Security.objects.filter(holdings__account__user=user).distinct()

        # Filter to those with no price or stale price
        # We need to find securities where the LATEST price is older than cutoff_time
        # or where NO price exists.
        from django.db.models import Max

        stale_securities = user_securities.annotate(
            latest_price_time=Max("prices__price_datetime")
        ).filter(
            models.Q(latest_price_time__isnull=True) | models.Q(latest_price_time__lt=cutoff_time)
        )

        return stale_securities

    @classmethod
    def get_price_at_datetime(cls, security: Security, target_datetime: datetime) -> Decimal | None:
        """
        Get price at or before specific datetime.

        This enables precise time-based queries like:
        "What was VTI's price at 2:30 PM on Jan 15, 2024?"

        Args:
            security: Security to get price for
            target_datetime: Exact datetime to get price for

        Returns:
            Price as Decimal, or None if no prices exist at or before datetime
        """
        price_record = cls.objects.filter(
            security=security, price_datetime__lte=target_datetime
        ).first()
        return price_record.price if price_record else None

    @classmethod
    def get_price_on_date(cls, security: Security, target_date: date) -> Decimal | None:
        """
        Get latest price on a specific date.

        Returns the most recent price recorded on that date.
        Useful for end-of-day calculations.

        Args:
            security: Security to get price for
            target_date: Date to get price for (uses all prices on this date)

        Returns:
            Latest price on that date as Decimal, or None if no prices on that date
        """
        from datetime import datetime, time

        from django.utils import timezone

        # Get timezone-aware start and end of day
        start_of_day = timezone.make_aware(datetime.combine(target_date, time.min))
        end_of_day = timezone.make_aware(datetime.combine(target_date, time.max))

        price_record = cls.objects.filter(
            security=security, price_datetime__gte=start_of_day, price_datetime__lte=end_of_day
        ).first()

        return price_record.price if price_record else None

    @classmethod
    def get_latest_prices_bulk(cls, securities: list[Security]) -> dict[int, Decimal]:
        """
        Get latest prices for multiple securities efficiently.

        Args:
            securities: List of Security objects

        Returns:
            Dictionary mapping security.id -> price
        """
        from django.db.models import Max

        # Get latest datetime for each security
        latest_datetimes = (
            cls.objects.filter(security__in=securities)
            .values("security")
            .annotate(latest_datetime=Max("price_datetime"))
        )

        # Build lookup dict: security_id -> latest_datetime
        datetime_lookup = {item["security"]: item["latest_datetime"] for item in latest_datetimes}

        # Fetch prices for those specific datetimes
        prices = (
            cls.objects.filter(
                security__in=securities,
            )
            .filter(
                # Use subquery to match each security's latest datetime
                models.Q(
                    *[
                        models.Q(security_id=sec_id, price_datetime=dt)
                        for sec_id, dt in datetime_lookup.items()
                    ],
                    _connector=models.Q.OR,
                )
            )
            .values("security_id", "price")
        )

        return {p["security_id"]: p["price"] for p in prices}


class Holding(models.Model):
    """Current investment holding in an account."""

    account = models.ForeignKey("Account", on_delete=models.CASCADE, related_name="holdings")
    security = models.ForeignKey(Security, on_delete=models.PROTECT, related_name="holdings")
    shares = models.DecimalField(
        max_digits=20, decimal_places=8, validators=[MinValueValidator(Decimal("0"))]
    )
    as_of_date = models.DateField(auto_now=True)

    objects = HoldingManager()

    class Meta:
        ordering = ["account", "security"]
        unique_together = ["account", "security"]

    def __str__(self) -> str:
        return f"{self.security.ticker} in {self.account.name} ({self.shares} shares)"

    # ===== Domain Methods =====
    # ===== New Price Properties (Using SecurityPrice) =====

    @property
    def latest_price(self) -> Decimal | None:
        """
        Get latest price from SecurityPrice table.
        Optimized to use annotated value from AllocationEngine if present.

        Returns:
            Latest price from SecurityPrice, or None if no price exists
        """
        # Check for annotated value from optimized prefetches
        if hasattr(self, "_annotated_latest_price"):
            return cast(Decimal | None, self._annotated_latest_price)

        return SecurityPrice.get_latest_price(self.security)

    @property
    def price_as_of_date(self) -> datetime | None:
        """
        Get datetime of the latest price.

        Returns:
            DateTime of latest SecurityPrice, or None if no price exists
        """
        latest = SecurityPrice.objects.filter(security=self.security).first()

        return latest.price_datetime if latest else None

    @property
    def market_value(self) -> Decimal:
        """
        Current market value of this holding.

        Uses latest_price (from SecurityPrice table).

        Returns 0.00 when no price is available.
        """
        price = self.latest_price
        if price is None:
            return Decimal("0.00")
        return (self.shares * price).quantize(Decimal("0.01"))

    @property
    def has_price(self) -> bool:
        """
        Whether this holding has a price available.

        Returns True if a SecurityPrice record exists for this holding's security.
        """
        return self.latest_price is not None

    @property
    def current_price(self) -> Decimal | None:
        """
        Legacy property for backward compatibility.
        Wrapper around latest_price.
        """
        return self.latest_price

    def calculate_target_value(self, account_total: Decimal, target_pct: Decimal) -> Decimal:
        """Calculate target dollar value for this holding.

        Target percentage is expressed on a 0-100 scale.
        """

        return account_total * target_pct / Decimal("100")

    def calculate_variance(self, target_value: Decimal) -> Decimal:
        """Calculate variance from target (positive = overweight)."""

        return self.market_value - target_value

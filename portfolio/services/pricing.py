"""
Pricing service for fetching and storing security prices.

This service fetches prices from external sources (yfinance) and stores
them in the centralized SecurityPrice table for historical tracking.

Key Design:
- price_datetime: Market time from data provider (used for lookups)
- fetched_at: Our fetch time (automatically set, audit trail)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction

import structlog

from portfolio.models import Holding, Security, SecurityPrice
from portfolio.services.market_data import MarketDataService
from users.models import CustomUser

logger = structlog.get_logger(__name__)


class PricingService:
    """
    Fetches and updates security prices from external sources.

    Updated to use SecurityPrice table for centralized price storage
    with full historical tracking at datetime precision.

    Stores both market timestamp (from data provider) and fetch timestamp
    (when we retrieved it) for complete audit trail.
    """

    def __init__(self, market_data: MarketDataService | None = None) -> None:
        self._market_data = market_data or MarketDataService()
        logger.debug("Initializing PricingService")

    def update_holdings_prices(
        self,
        user: CustomUser,
        override_datetime: datetime | None = None,  # For testing
    ) -> dict[str, Decimal]:
        """
        Fetch current prices and store in SecurityPrice table.

        This method:
        1. Finds all securities held by user
        2. Fetches prices with market timestamps from data service
        3. Stores in SecurityPrice table (price_datetime = market time)

        The fetched_at timestamp is automatically set by the model and
        represents when we retrieved the data (audit trail).

        Args:
            user: User whose holdings to update
            override_datetime: Optional datetime override (for testing only)

        Returns:
            Dictionary mapping ticker -> price (without timestamp)
        """
        # Get all holdings for user with securities
        holdings = Holding.objects.get_for_pricing(user)

        # Get unique securities
        securities = {h.security for h in holdings}
        tickers = [s.ticker for s in securities]

        if not tickers:
            logger.info("No tickers to update for user", user_id=user.id)
            return {}

        # Fetch prices WITH market timestamps from data service
        price_data = self._market_data.get_prices(tickers)

        if not price_data:
            logger.warning("No prices returned from market data service")
            return {}

        # Create a mapping from ticker to security object for efficient lookup
        ticker_to_security = {s.ticker: s for s in securities}

        # Store prices in SecurityPrice table
        with transaction.atomic():
            for ticker in tickers:
                if ticker in price_data:
                    price, market_time = price_data[ticker]

                    # Get security for this ticker
                    security = ticker_to_security.get(ticker)
                    if not security:
                        logger.warning(f"No security found for ticker: {ticker}")
                        continue

                    # Use override if provided (for testing)
                    if override_datetime:
                        market_time = override_datetime

                    # Create or update SecurityPrice record
                    # fetched_at is automatically set by auto_now_add
                    SecurityPrice.objects.update_or_create(
                        security=security,
                        price_datetime=market_time,  # Market time from Yahoo
                        defaults={"price": price, "source": "yfinance"},
                    )

                    logger.debug(f"Stored price for {ticker}: {price} at {market_time}")
                else:
                    logger.warning(f"No price returned for {ticker}")

        logger.info(
            f"Updated prices for user {user.id}: {len([t for t in tickers if t in price_data])} securities"
        )

        # Return prices as dict[ticker, price] (timestamps available via SecurityPrice queries)
        return {t: p for t, (p, _) in price_data.items()}

    def update_holdings_prices_if_stale(
        self, user: CustomUser, max_age: timedelta = timedelta(minutes=5)
    ) -> dict[str, Any]:
        """
        Update prices only for securities with stale data.

        This is the preferred method for routine price updates as it prevents
        unnecessary API calls and rate limiting.

        Args:
            user: User whose holdings to check
            max_age: Maximum price age before refresh (default: 5 minutes)

        Returns:
            dict with:
                - updated_count: Number of securities updated
                - skipped_count: Number of securities with fresh prices
                - errors: List of tickers that failed to update
        """
        # Get securities that need updating
        stale_securities = SecurityPrice.get_stale_securities(user, max_age)
        stale_count = stale_securities.count()

        # Calculate how many are current
        total_securities_count = (
            Security.objects.filter(holdings__account__user=user).distinct().count()
        )
        skipped_count = total_securities_count - stale_count

        if stale_count == 0:
            logger.info(
                "all_prices_fresh",
                user_id=user.id,
                max_age_minutes=max_age.total_seconds() / 60,
            )
            return {
                "updated_count": 0,
                "skipped_count": skipped_count,
                "errors": [],
            }

        logger.info(
            "updating_stale_prices",
            user_id=user.id,
            stale_count=stale_count,
            max_age_minutes=max_age.total_seconds() / 60,
        )

        tickers = [s.ticker for s in stale_securities]

        # Fetch prices WITH market timestamps from data service
        price_data = self._market_data.get_prices(tickers)

        if not price_data:
            logger.warning("No prices returned from market data service")
            return {"updated_count": 0, "skipped_count": 0, "errors": tickers}

        # Create a mapping from ticker to security object for efficient lookup
        ticker_to_security = {s.ticker: s for s in stale_securities}

        errors = []
        updated_count = 0

        # Store prices in SecurityPrice table
        with transaction.atomic():
            for ticker in tickers:
                if ticker in price_data:
                    price, market_time = price_data[ticker]

                    # Get security for this ticker
                    security = ticker_to_security.get(ticker)
                    if not security:
                        # Should not happen as we got tickers from stale_securities
                        continue

                    # Create or update SecurityPrice record
                    SecurityPrice.objects.update_or_create(
                        security=security,
                        price_datetime=market_time,
                        defaults={"price": price, "source": "yfinance"},
                    )
                    updated_count += 1
                    logger.debug(f"Stored price for {ticker}: {price} at {market_time}")
                else:
                    errors.append(ticker)
                    logger.warning(f"No price returned for {ticker}")

        # Calculate how many were fresh
        # (Total user securities - stale ones)
        total_securities_count = (
            Security.objects.filter(holdings__account__user=user).distinct().count()
        )
        skipped_count = total_securities_count - stale_count

        logger.info(
            "price_update_complete",
            user_id=user.id,
            updated_count=updated_count,
            skipped_count=skipped_count,
            error_count=len(errors),
        )

        return {
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "errors": errors,
        }

    def get_price_at_datetime(
        self, security: Security, target_datetime: datetime
    ) -> Decimal | None:
        """
        Get price for a security at a specific datetime.

        Uses SecurityPrice table to find price at or before target_datetime.
        This enables precise historical price lookups.

        Args:
            security: Security to get price for
            target_datetime: Datetime to get price for

        Returns:
            Price as Decimal, or None if no price available
        """
        return SecurityPrice.get_price_at_datetime(security, target_datetime)

    def get_price_for_date(self, security: Security, target_date: date) -> Decimal | None:
        """
        Get latest price on a specific date.

        Returns the most recent price recorded on that date.
        Useful for end-of-day calculations.

        Args:
            security: Security to get price for
            target_date: Date to get price for

        Returns:
            Latest price on that date as Decimal, or None if no price on that date
        """
        return SecurityPrice.get_price_on_date(security, target_date)

    def get_latest_prices_bulk(self, securities: list[Security]) -> dict[Security, Decimal]:
        """
        Get latest prices for multiple securities efficiently.

        Args:
            securities: List of Security objects

        Returns:
            Dictionary mapping Security -> price
        """
        price_dict = SecurityPrice.get_latest_prices_bulk(securities)

        # Convert security_id -> Security object mapping
        security_lookup = {s.id: s for s in securities}

        return {security_lookup[sec_id]: price for sec_id, price in price_dict.items()}

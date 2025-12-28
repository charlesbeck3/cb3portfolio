import logging
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class MarketDataService:
    @staticmethod
    def get_prices(tickers: list[str]) -> dict[str, tuple[Decimal, datetime]]:
        """
        Fetch current prices with their market timestamps.

        Returns tuple of (price, market_timestamp) for each ticker.
        The timestamp reflects when the market reported this price,
        not when we fetched it.

        Args:
            tickers: List of ticker symbols to fetch

        Returns:
            Dictionary mapping ticker -> (price, market_timestamp)

        Example:
            >>> prices = get_prices(['VTI', 'BND'])
            >>> prices['VTI']
            (Decimal('245.67'), datetime(2024, 1, 15, 16, 0, 0, tzinfo=<EST>))
        """
        if not tickers:
            return {}

        price_map: dict[str, tuple[Decimal, datetime]] = {}

        # Handle cash-equivalent tickers separately
        cash_tickers = {"CASH", "IBOND"}
        params_tickers = []

        for ticker in tickers:
            if ticker in cash_tickers:
                # Cash is always $1.00 at current time
                price_map[ticker] = (Decimal("1.00"), timezone.now())
            else:
                params_tickers.append(ticker)

        if not params_tickers:
            return price_map

        try:
            # Fetch data for all tickers at once
            data = yf.download(params_tickers, period="1d", progress=False, auto_adjust=True)[
                "Close"
            ]

            if len(params_tickers) == 1:
                # Single ticker case
                ticker = params_tickers[0]
                try:
                    if not data.empty:
                        # Get last price and its timestamp
                        last_idx = data.index[-1]
                        price_value = data.iloc[-1]

                        # Extract timestamp from pandas index
                        timestamp = pd.Timestamp(last_idx).to_pydatetime()

                        # Normalize timestamp (handle timezone, market close time)
                        timestamp = MarketDataService._normalize_timestamp(timestamp)

                        # Convert price to Decimal
                        val = price_value.item() if hasattr(price_value, "item") else price_value

                        # Check for NaN
                        if val == val:  # NaN check
                            price_map[ticker] = (Decimal(str(val)), timestamp)
                        else:
                            logger.warning(f"Price for {ticker} is NaN")

                except Exception as e:
                    logger.warning(f"Could not extract price for {ticker}: {e}")
            else:
                # Multiple tickers case
                if not data.empty:
                    latest_prices = data.iloc[-1]

                    # Get timestamp from index
                    timestamp = pd.Timestamp(data.index[-1]).to_pydatetime()
                    timestamp = MarketDataService._normalize_timestamp(timestamp)

                    for ticker in params_tickers:
                        try:
                            price_value = latest_prices[ticker]
                            val = (
                                price_value.item() if hasattr(price_value, "item") else price_value
                            )

                            # Check for NaN
                            if val == val:
                                price_map[ticker] = (Decimal(str(val)), timestamp)
                            else:
                                logger.warning(f"Price for {ticker} is NaN")
                        except Exception as e:
                            logger.warning(f"Could not extract price for {ticker}: {e}")

        except Exception as e:
            logger.error(f"Error fetching prices: {e}")

        return price_map

    @staticmethod
    def _normalize_timestamp(timestamp: datetime) -> datetime:
        """
        Normalize timestamp from Yahoo Finance to market time.

        Yahoo Finance quirks:
        - Daily data returns date at midnight (00:00)
        - Should represent market close time (4 PM ET)
        - Already returns timezone-aware datetimes in market time

        Args:
            timestamp: Raw timestamp from Yahoo Finance

        Returns:
            Normalized, timezone-aware datetime representing market time
        """
        import pytz

        # If timezone-naive, assume it's US Eastern Time (market time)
        if timestamp.tzinfo is None:
            est = pytz.timezone("America/New_York")
            timestamp = est.localize(timestamp)

        # If midnight timestamp (daily data), set to market close (4 PM ET)
        if timestamp.hour == 0 and timestamp.minute == 0 and timestamp.second == 0:
            # Preserve the date and timezone, just update time to 4 PM
            timestamp = timestamp.replace(hour=16, minute=0, second=0, microsecond=0)

        return timestamp

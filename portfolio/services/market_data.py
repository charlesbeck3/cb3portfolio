import logging
from decimal import Decimal

import yfinance as yf

logger = logging.getLogger(__name__)


class MarketDataService:
    @staticmethod
    def get_prices(tickers: list[str]) -> dict[str, Decimal]:
        """
        Fetch current prices for a list of tickers.
        Returns a dictionary mapping ticker -> price.
        """
        if not tickers:
            return {}

        price_map: dict[str, Decimal] = {}

        # Handle cash-equivalent tickers separately - they're always $1.00
        cash_tickers = {"CASH", "IBOND"}
        params_tickers = []

        for ticker in tickers:
            if ticker in cash_tickers:
                price_map[ticker] = Decimal("1.00")
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
                # If single ticker, 'data' might be a Series or DataFrame depending on yfinance version/args
                # yfinance 0.2+ usually returns DataFrame with MultiIndex if group_by='ticker' (default is column)
                # But with simple download of 1 ticker, it might be just a DataFrame with columns Open, High, etc.
                # Let's be safe and fetch the last value.
                ticker = params_tickers[0]
                try:
                    price = data.iloc[-1]
                    # If it's a series (one ticker), price is the value.
                    # If it's a dataframe (multiple columns for one ticker?), we selected 'Close' above.
                    # If 'Close' returned a Series (one ticker), iloc[-1] is the price.
                    val = price.item() if hasattr(price, "item") else price

                    # Check for NaN
                    if val != val:  # NaN check
                        logger.warning(f"Price for {ticker} is NaN")
                    else:
                        price_map[ticker] = Decimal(str(val))
                except Exception:
                    logger.warning(f"Could not extract price for {ticker}")

            else:
                # Multiple tickers, 'data' is a DataFrame where columns are tickers
                # Get the last row (latest prices)
                latest_prices = data.iloc[-1]
                for ticker in params_tickers:
                    try:
                        price = latest_prices[ticker]
                        val = price.item() if hasattr(price, "item") else price

                        # Check for NaN
                        if val != val:  # NaN check
                            logger.warning(f"Price for {ticker} is NaN")
                            continue

                        price_map[ticker] = Decimal(str(val))
                    except Exception:
                        logger.warning(f"Could not extract price for {ticker}")

        except Exception as e:
            logger.error(f"Error updating prices: {e}")

        return price_map

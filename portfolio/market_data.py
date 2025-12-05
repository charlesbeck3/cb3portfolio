import logging
from decimal import Decimal
from typing import Any

import yfinance as yf

from portfolio.models import Holding

logger = logging.getLogger(__name__)


class MarketDataService:
    @staticmethod
    def update_prices(user: Any) -> None:
        """
        Fetch current prices for all securities held by the user and update Holding.current_price.
        """
        holdings = Holding.objects.filter(account__user=user).select_related('security')
        tickers = list({h.security.ticker for h in holdings})

        if not tickers:
            return

        # Handle cash-equivalent tickers separately - they're always $1.00
        cash_tickers = {'CASH', 'IBOND'}
        cash_holdings = [h for h in holdings if h.security.ticker in cash_tickers]
        for holding in cash_holdings:
            holding.current_price = Decimal('1.00')
            holding.save(update_fields=['current_price'])

        # Remove cash tickers from list to fetch from yfinance
        tickers = [t for t in tickers if t not in cash_tickers]

        if not tickers:
            return

        try:
            # Fetch data for all tickers at once
            data = yf.download(tickers, period="1d", progress=False)['Close']

            # If only one ticker, data is a Series, otherwise DataFrame
            # We need to handle both cases or ensure we access it correctly

            # Create a map of ticker -> price
            price_map = {}
            if len(tickers) == 1:
                # If single ticker, 'data' might be a Series or DataFrame depending on yfinance version/args
                # yfinance 0.2+ usually returns DataFrame with MultiIndex if group_by='ticker' (default is column)
                # But with simple download of 1 ticker, it might be just a DataFrame with columns Open, High, etc.
                # Let's be safe and fetch the last value.
                ticker = tickers[0]
                try:
                    price = data.iloc[-1]
                    # If it's a series (one ticker), price is the value.
                    # If it's a dataframe (multiple columns for one ticker?), we selected 'Close' above.
                    # If 'Close' returned a Series (one ticker), iloc[-1] is the price.
                    val = price.item() if hasattr(price, 'item') else price

                    # Check for NaN
                    if val != val: # NaN check
                         logger.warning(f"Price for {ticker} is NaN")
                    else:
                        price_map[ticker] = Decimal(str(val))
                except Exception:
                    logger.warning(f"Could not extract price for {ticker}")

            else:
                # Multiple tickers, 'data' is a DataFrame where columns are tickers
                # Get the last row (latest prices)
                latest_prices = data.iloc[-1]
                for ticker in tickers:
                    try:
                        price = latest_prices[ticker]
                        val = price.item() if hasattr(price, 'item') else price

                        # Check for NaN
                        if val != val: # NaN check
                             logger.warning(f"Price for {ticker} is NaN")
                             continue

                        price_map[ticker] = Decimal(str(val))
                    except Exception:
                         logger.warning(f"Could not extract price for {ticker}")

            # Update holdings
            for holding in holdings:
                if holding.security.ticker in price_map:
                    holding.current_price = price_map[holding.security.ticker]
                    holding.save(update_fields=['current_price'])

        except Exception as e:
            logger.error(f"Error updating prices: {e}")

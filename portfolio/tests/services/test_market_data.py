from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

import pytest

from portfolio.services.market_data import MarketDataService


class MarketDataServiceTests(TestCase):
    @patch("portfolio.services.market_data.yf.download")
    def test_get_prices(self, mock_download: MagicMock) -> None:
        # Mock yfinance response - create real pandas objects
        from datetime import datetime

        import pandas as pd

        # Create a real pandas Series with the prices (multi-ticker case)
        # yf.download returns a DataFrame, and data["Close"] gives us the Close column
        # For multiple tickers, data["Close"].iloc[-1] gives us a Series with ticker symbols as index
        mock_close_series = pd.Series(
            data=[210.00, 85.00], index=pd.Index(["VTI", "BND"], name="Ticker")
        )
        # The series name is the timestamp
        mock_close_series.name = datetime(2024, 1, 1, 16, 0, 0)

        # Create a mock DataFrame that behaves like yfinance output
        mock_df = MagicMock()
        # When code does data["Close"]
        mock_close_col = MagicMock()
        mock_close_col.iloc.__getitem__.return_value = mock_close_series
        mock_close_col.index = pd.DatetimeIndex([datetime(2024, 1, 1, 16, 0, 0)])
        mock_close_col.empty = False

        mock_df.__getitem__.return_value = mock_close_col
        mock_download.return_value = mock_df

        tickers = ["VTI", "BND", "CASH"]
        prices = MarketDataService.get_prices(tickers)

        # Verify yfinance was called correctly
        self.assertTrue(mock_download.called)
        filtered_tickers_arg = mock_download.call_args[0][0]
        self.assertIn("VTI", filtered_tickers_arg)
        self.assertIn("BND", filtered_tickers_arg)
        self.assertNotIn("CASH", filtered_tickers_arg)

        # get_prices now returns (price, datetime) tuples
        self.assertEqual(prices["VTI"][0], Decimal("210.0"))  # price
        self.assertEqual(prices["BND"][0], Decimal("85.0"))  # price
        self.assertEqual(prices["CASH"][0], Decimal("1.00"))  # price
        # Check that datetimes are returned
        self.assertIsNotNone(prices["VTI"][1])
        self.assertIsNotNone(prices["BND"][1])
        self.assertIsNotNone(prices["CASH"][1])

    def test_get_prices_empty(self) -> None:
        prices = MarketDataService.get_prices([])
        self.assertEqual(prices, {})


@pytest.mark.integration
@pytest.mark.services
class TestMarketDataServiceCoverage:
    """Additional tests to improve coverage for MarketDataService."""

    @patch("portfolio.services.market_data.yf.download")
    def test_single_ticker_fetch(self, mock_download):
        """Test fetching a single ticker (different code path)."""
        from datetime import datetime

        import pandas as pd

        # Setup mock for single ticker
        # yf.download for single ticker returns DataFrame where columns are just the fields (Open, High, Low, Close...)
        # NOT MultiIndex columns like (Close, Ticker).
        # Actually in auto_adjust=True, it returns just the columns.

        # We need to match how the service consumes it.
        # Line 55: data = yf.download(...)["Close"]
        # Line 65: last_idx = data.index[-1]
        # Line 66: price_value = data.iloc[-1]

        # When fetching single ticker, data["Close"] is a Series.
        timestamp = datetime(2024, 1, 1, 16, 0, 0)
        mock_series = pd.Series(data=[150.00], index=pd.DatetimeIndex([timestamp]))

        mock_df = MagicMock()
        mock_df.__getitem__.return_value = mock_series  # This is data["Close"]

        mock_download.return_value = mock_df

        prices = MarketDataService.get_prices(["AAPL"])

        assert "AAPL" in prices
        assert prices["AAPL"][0] == Decimal("150.0")

    @patch("portfolio.services.market_data.yf.download")
    def test_api_exception_handling(self, mock_download):
        """Test that API errors are caught and logged."""
        mock_download.side_effect = Exception("API Error")

        # Should not raise, just return empty/partial
        prices = MarketDataService.get_prices(["VTI"])

        assert prices == {}

    def test_normalize_timestamp_midnight(self):
        """Test timestamp normalization for midnight (daily data)."""
        from datetime import datetime

        import pytz

        # Midnight naive (assumed EST)
        dt = datetime(2024, 1, 1, 0, 0, 0)
        normalized = MarketDataService._normalize_timestamp(dt)

        # Should be set to 16:00 EST
        est = pytz.timezone("America/New_York")
        expected = est.localize(datetime(2024, 1, 1, 16, 0, 0))

        assert normalized == expected

    def test_normalize_timestamp_naive_market_time(self):
        """Test timestamp normalization for naive market time."""
        from datetime import datetime

        import pytz

        # 16:00 naive
        dt = datetime(2024, 1, 1, 16, 0, 0)
        normalized = MarketDataService._normalize_timestamp(dt)

        est = pytz.timezone("America/New_York")
        expected = est.localize(dt)

        assert normalized == expected

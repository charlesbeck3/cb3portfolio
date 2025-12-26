from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from portfolio.market_data import MarketDataService


class MarketDataServiceTests(TestCase):
    @patch("portfolio.market_data.yf.download")
    def test_get_prices(self, mock_download: MagicMock) -> None:
        # Mock yfinance response
        mock_data = MagicMock()
        # Mocking .iloc[-1] to return a dict-like object or series for multiple tickers
        # When multiple tickers are downloaded, yfinance returns a DataFrame.
        # .iloc[-1] on that DataFrame returns a Series indexed by ticker.
        mock_data.iloc.__getitem__.side_effect = lambda key: {"VTI": 210.00, "BND": 85.00}[key]

        # We need to structure the mock so that 'Close' returns an object that .iloc[-1] works on.
        # And that result behaves like a dict or Series.
        mock_close = MagicMock()
        mock_close.iloc.__getitem__.return_value = {"VTI": 210.00, "BND": 85.00}

        # Simulating that accessing ['VTI'] on the result of .iloc[-1] returns the float
        # But wait, our code does: price = latest_prices[ticker]
        # So latest_prices needs to be subscriptable.
        mock_latest_prices = MagicMock()
        mock_latest_prices.__getitem__.side_effect = lambda k: {"VTI": 210.00, "BND": 85.00}[k]

        mock_df = MagicMock()
        mock_df.iloc.__getitem__.return_value = mock_latest_prices

        mock_download.return_value = {"Close": mock_df}

        tickers = ["VTI", "BND", "CASH"]
        prices = MarketDataService.get_prices(tickers)

        # distinct tickers to yfinance should be VTI, BND. CASH is handled separately.
        filtered_tickers_arg = mock_download.call_args[0][0]
        self.assertIn("VTI", filtered_tickers_arg)
        self.assertIn("BND", filtered_tickers_arg)
        self.assertNotIn("CASH", filtered_tickers_arg)

        self.assertEqual(prices["VTI"], Decimal("210.0"))
        self.assertEqual(prices["BND"], Decimal("85.0"))
        self.assertEqual(prices["CASH"], Decimal("1.00"))

    def test_get_prices_empty(self) -> None:
        prices = MarketDataService.get_prices([])
        self.assertEqual(prices, {})

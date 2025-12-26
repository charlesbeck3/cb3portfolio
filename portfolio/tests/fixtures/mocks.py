from collections.abc import Callable, Generator
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_market_prices() -> Callable[[dict[str, Decimal]], MagicMock]:
    """
    Fixture that mocks MarketDataService.get_prices with stable prices.

    Usage:
        def test_something(self, mock_market_prices):
            mock_market_prices({"VTI": Decimal("100.00")})
            # ... test code ...
    """
    def _mock_prices(prices: dict[str, Decimal]) -> MagicMock:
        patcher = patch("portfolio.services.MarketDataService.get_prices")
        mock = patcher.start()
        mock.return_value = prices
        return mock

    # We don't yield here because the function itself is the fixture value
    return _mock_prices


@pytest.fixture
def stable_test_prices() -> Generator[MagicMock]:
    """Pre-configured mock with standard test prices."""
    with patch("portfolio.services.MarketDataService.get_prices") as mock:
        mock.return_value = {
            "VTI": Decimal("100.00"),
            "VXUS": Decimal("50.00"),
            "BND": Decimal("80.00"),
            "VGSH": Decimal("60.00"),
        }
        yield mock

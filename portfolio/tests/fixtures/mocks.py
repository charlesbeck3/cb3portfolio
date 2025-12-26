"""
Mock fixtures for external dependencies.

Provides consistent mocking for:
- Market data prices (MarketDataService)
- External API calls
- Time-dependent operations
"""

from collections.abc import Callable, Generator
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# MARKET DATA MOCKS
# ============================================================================


@pytest.fixture
def mock_market_prices(request: Any) -> Callable[[dict[str, Decimal]], MagicMock]:
    """
    Fixture that mocks MarketDataService.get_prices with custom prices.

    This is a fixture factory - it returns a function that creates the mock.
    Use this when you need different prices in different parts of your test.

    Usage:
        def test_something(mock_market_prices):
            # Set up custom prices
            mock = mock_market_prices({"VTI": Decimal("100.00"), "BND": Decimal("80.00")})

            # Run test code...

            # Verify the mock was called
            mock.assert_called_once()

    Note: Patches are automatically cleaned up between tests.
    """

    def _mock_prices(prices: dict[str, Decimal]) -> MagicMock:
        patcher = patch("portfolio.services.MarketDataService.get_prices")
        mock = patcher.start()
        mock.return_value = prices
        request.addfinalizer(patcher.stop)
        return mock

    return _mock_prices


@pytest.fixture
def stable_test_prices() -> Generator[MagicMock]:
    """
    Pre-configured mock with standard test prices.

    Use this fixture when you don't care about specific prices and just
    need MarketDataService to return something reasonable.

    Provides:
    - VTI: $100.00
    - VXUS: $50.00
    - BND: $80.00
    - VGSH: $60.00
    - CASH: $1.00

    Usage:
        def test_something(stable_test_prices):
            # Prices are already mocked
            response = client.get('/dashboard/')
            # ... assertions ...
    """
    with patch("portfolio.services.MarketDataService.get_prices") as mock:
        mock.return_value = {
            "VTI": Decimal("100.00"),
            "VXUS": Decimal("50.00"),
            "BND": Decimal("80.00"),
            "VGSH": Decimal("60.00"),
            "CASH": Decimal("1.00"),
        }
        yield mock


@pytest.fixture
def zero_prices() -> Generator[MagicMock]:
    """
    Mock that returns zero prices for all securities.

    Useful for testing edge cases where pricing data is unavailable.

    Usage:
        def test_missing_prices(zero_prices):
            # All securities will have price = 0
            engine.calculate_allocations(portfolio)
    """
    with patch("portfolio.services.MarketDataService.get_prices") as mock:
        mock.return_value = {}
        yield mock


@pytest.fixture
def volatile_prices() -> Generator[MagicMock]:
    """
    Mock with volatile/extreme prices for stress testing.

    Tests calculation robustness with:
    - Very high prices
    - Very low prices
    - Many decimal places
    """
    with patch("portfolio.services.MarketDataService.get_prices") as mock:
        mock.return_value = {
            "VTI": Decimal("9999.9999"),
            "VXUS": Decimal("0.0001"),
            "BND": Decimal("123.456789"),
            "CASH": Decimal("1.00"),
        }
        yield mock


# ============================================================================
# CONTEXT MANAGERS FOR DJANGO TESTCASE
# ============================================================================


class MockMarketPrices:
    """
    Context manager for mocking market prices in Django TestCase tests.

    This is for TestCase classes that can't use pytest fixtures.

    Usage:
        class MyTest(TestCase):
            def test_something(self):
                with MockMarketPrices({"VTI": Decimal("100.00")}):
                    response = self.client.get('/dashboard/')
                    # Prices are mocked within this block
    """

    def __init__(self, prices: dict[str, Decimal]):
        self.prices = prices
        self.patcher: Any = None
        self.mock: Any = None

    def __enter__(self) -> MagicMock:
        self.patcher = patch("portfolio.services.MarketDataService.get_prices")
        self.mock = self.patcher.start()
        self.mock.return_value = self.prices
        return self.mock

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.patcher:
            self.patcher.stop()


# ============================================================================
# HELPER UTILITIES
# ============================================================================


def get_standard_prices() -> dict[str, Decimal]:
    """
    Get the standard test price dictionary.

    Useful when you need the prices as a dict rather than a mock.

    Returns:
        Dict mapping ticker symbols to prices
    """
    return {
        "VTI": Decimal("100.00"),
        "VXUS": Decimal("50.00"),
        "BND": Decimal("80.00"),
        "VGSH": Decimal("60.00"),
        "CASH": Decimal("1.00"),
    }

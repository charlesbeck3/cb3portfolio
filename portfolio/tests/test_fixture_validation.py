"""
Validation tests for new fixture system.

Run with: uv run pytest portfolio/tests/test_fixture_validation.py -v
"""

from decimal import Decimal

import pytest


@pytest.mark.django_db
class TestFixtureSystem:
    """Validate that all new fixtures work correctly."""

    def test_base_system_data_fixture(self, base_system_data):
        """Verify base_system_data provides all expected attributes."""
        assert base_system_data.institution is not None
        assert base_system_data.type_roth is not None
        assert base_system_data.asset_class_us_equities is not None
        assert base_system_data.vti is not None

    def test_test_user_fixture(self, test_user):
        """Verify test_user fixture creates a valid user."""
        assert test_user.username == "testuser"
        assert test_user.check_password("password")

    def test_test_portfolio_fixture(self, test_portfolio):
        """Verify test_portfolio contains expected keys."""
        assert 'user' in test_portfolio
        assert 'portfolio' in test_portfolio
        assert 'system' in test_portfolio
        assert test_portfolio['portfolio'].user == test_portfolio['user']

    def test_simple_holdings_fixture(self, simple_holdings):
        """Verify simple_holdings creates holdings correctly."""
        assert simple_holdings['holding'] is not None
        # shares=10.00 * price=100.00 = 1000.00
        # Check market_value as Decimal
        assert simple_holdings['holding'].market_value == Decimal("1000")

    def test_stable_prices_fixture(self, stable_test_prices):
        """Verify stable_test_prices mocks MarketDataService."""
        from portfolio.services import MarketDataService

        prices = MarketDataService.get_prices(["VTI", "BND"])
        assert prices["VTI"] == Decimal("100.00")
        assert prices["BND"] == Decimal("80.00")

    def test_mock_market_prices_factory(self, mock_market_prices):
        """Verify mock_market_prices factory works."""
        custom_prices = {"TEST": Decimal("999.99")}
        mock = mock_market_prices(custom_prices)

        from portfolio.services import MarketDataService
        result = MarketDataService.get_prices(["TEST"])

        assert result == custom_prices
        mock.assert_called_once()

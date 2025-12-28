"""
Tests for security pricing service.

Tests: portfolio/services/pricing.py
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from django.utils import timezone as tz

import pytest

from portfolio.models import Account, Holding, Institution, SecurityPrice
from portfolio.services import PricingService


@pytest.mark.services
@pytest.mark.integration
class TestPricingService:
    """Tests for the security pricing service."""

    @pytest.fixture
    def pricing_setup(self, test_user, base_system_data):
        from portfolio.models import Portfolio as PortfolioModel

        system = base_system_data
        portfolio = PortfolioModel.objects.create(user=test_user, name="Pricing Test Portfolio")
        institution = Institution.objects.create(name="Test Institution")

        account = Account.objects.create(
            user=test_user,
            name="Roth IRA",
            portfolio=portfolio,
            account_type=system.type_roth,
            institution=institution,
        )

        # Use VTI for testing
        security = system.vti

        return {
            "user": test_user,
            "portfolio": portfolio,
            "account": account,
            "security": security,
            "system": system,
        }

    def test_update_holdings_prices_no_holdings_returns_empty(self, pricing_setup):
        """Verify handling of account with no holdings."""
        mock_market_data = MagicMock()
        service = PricingService(market_data=mock_market_data)

        prices = service.update_holdings_prices(pricing_setup["user"])

        assert prices == {}
        mock_market_data.get_prices.assert_not_called()

    def test_update_holdings_prices_updates_prices(self, pricing_setup):
        """Verify service correctly updates holding prices from market data."""
        setup = pricing_setup
        holding = Holding.objects.create(
            account=setup["account"],
            security=setup["security"],
            shares=Decimal("10.0"),
        )

        mock_market_data = MagicMock()
        mock_dt = tz.make_aware(datetime(2024, 1, 1, 12, 0, 0))
        mock_market_data.get_prices.return_value = {
            setup["security"].ticker: (Decimal("210.00"), mock_dt)
        }

        service = PricingService(market_data=mock_market_data)
        result = service.update_holdings_prices(setup["user"])

        # Check result
        assert result == {setup["security"].ticker: Decimal("210.00")}

        # Check database
        price_obj = SecurityPrice.objects.filter(security=setup["security"]).latest(
            "price_datetime"
        )
        assert price_obj.price == Decimal("210.00")
        assert holding.latest_price == Decimal("210.00")
        mock_market_data.get_prices.assert_called_once()

"""
Tests for security pricing service.

Tests: portfolio/services/pricing.py
"""

from datetime import datetime, timedelta
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


@pytest.mark.django_db
@pytest.mark.services
@pytest.mark.integration
class TestPriceCaching:
    """Test price caching and staleness detection."""

    @pytest.fixture
    def pricing_service(self):
        """Create pricing service instance."""
        return PricingService()

    def test_is_stale_no_price_datetime(self, simple_holdings):
        """Test that security price with no datetime is considered stale."""
        vti = simple_holdings["system"].vti
        # Create a price without a datetime (though DB usually enforces this, let's test logic)
        price = SecurityPrice(
            security=vti,
            price=Decimal("100.00"),
            price_datetime=None,
            source="test",
        )
        assert price.is_stale(max_age=timedelta(minutes=5)) is True

    def test_is_stale_fresh_price(self, simple_holdings):
        """Test that recently updated price is not stale."""
        vti = simple_holdings["system"].vti
        price = SecurityPrice.objects.create(
            security=vti,
            price=Decimal("100.00"),
            price_datetime=tz.now(),
            source="test",
        )
        assert price.is_stale(max_age=timedelta(minutes=5)) is False

    def test_is_stale_old_price(self, simple_holdings):
        """Test that old price is considered stale."""
        vti = simple_holdings["system"].vti
        old_time = tz.now() - timedelta(minutes=10)
        price = SecurityPrice.objects.create(
            security=vti,
            price=Decimal("100.00"),
            price_datetime=old_time,
            source="test",
        )
        assert price.is_stale(max_age=timedelta(minutes=5)) is True

    def test_get_stale_securities_finds_stale(self, test_user, multi_account_holdings):
        """Test that get_stale_securities correctly identifies stale securities."""
        vti = multi_account_holdings["system"].vti
        bnd = multi_account_holdings["system"].bnd

        # Clear existing prices to start clean
        SecurityPrice.objects.filter(security__in=[vti, bnd]).delete()

        # VTI has fresh price
        SecurityPrice.objects.create(
            security=vti,
            price=Decimal("100.00"),
            price_datetime=tz.now(),
            source="test",
        )

        # BND has stale price
        SecurityPrice.objects.create(
            security=bnd,
            price=Decimal("80.00"),
            price_datetime=tz.now() - timedelta(minutes=10),
            source="test",
        )

        stale = SecurityPrice.get_stale_securities(test_user, max_age=timedelta(minutes=5))
        assert vti not in stale
        assert bnd in stale

    def test_get_stale_securities_no_price(self, test_user, simple_holdings):
        """Test that get_stale_securities identifies securities with no price."""
        vti = simple_holdings["system"].vti
        SecurityPrice.objects.filter(security=vti).delete()

        stale = SecurityPrice.get_stale_securities(test_user, max_age=timedelta(minutes=5))
        assert vti in stale

    def test_update_if_stale_skips_fresh_prices(
        self, pricing_service, test_user, simple_holdings, monkeypatch
    ):
        """Test that fresh prices are not updated."""
        vti = simple_holdings["system"].vti
        # Clear existing prices to start clean
        SecurityPrice.objects.filter(security=vti).delete()

        SecurityPrice.objects.create(
            security=vti,
            price=Decimal("100.00"),
            price_datetime=tz.now(),
            source="test",
        )

        # Mock the get_prices method
        get_prices_called = False

        def mock_get_prices(self, tickers):
            nonlocal get_prices_called
            get_prices_called = True
            return {}

        monkeypatch.setattr(
            "portfolio.services.market_data.MarketDataService.get_prices", mock_get_prices
        )

        result = pricing_service.update_holdings_prices_if_stale(test_user)

        assert result["updated_count"] == 0
        assert result["skipped_count"] >= 1
        assert get_prices_called is False

    def test_update_if_stale_updates_old_prices(
        self, pricing_service, test_user, simple_holdings, monkeypatch
    ):
        """Test that stale prices are updated."""
        vti = simple_holdings["system"].vti
        # Clear existing prices to start clean
        SecurityPrice.objects.filter(security=vti).delete()

        old_time = tz.now() - timedelta(minutes=10)
        SecurityPrice.objects.create(
            security=vti,
            price=Decimal("100.00"),
            price_datetime=old_time,
            source="test",
        )

        mock_market_time = tz.now()

        def mock_get_prices(self, tickers):
            assert "VTI" in tickers
            return {"VTI": (Decimal("105.00"), mock_market_time)}

        monkeypatch.setattr(
            "portfolio.services.market_data.MarketDataService.get_prices", mock_get_prices
        )

        result = pricing_service.update_holdings_prices_if_stale(test_user)

        assert result["updated_count"] == 1
        assert "VTI" not in result["errors"]

        # Verify DB update
        latest = SecurityPrice.objects.filter(security=vti).first()
        assert latest.price == Decimal("105.00")
        assert latest.price_datetime == mock_market_time

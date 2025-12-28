from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

import pytest

from portfolio.models import Account, AssetClass, Holding, Institution
from portfolio.services import PricingService

from ..base import PortfolioTestMixin

User = get_user_model()


@pytest.mark.services
@pytest.mark.integration
class PricingServiceTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.institution = Institution.objects.create(name="Test Institution")
        self.asset_class = AssetClass.objects.create(
            # Use existing US Equities or create if testing isolation
            name="US Equities Test",
            category=self.category_us_equities,
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            portfolio=self.portfolio,
            account_type=self.type_roth,
            institution=self.institution,
        )
        self.vti.asset_class = self.asset_class
        self.vti.save()
        self.security = self.vti

    def test_update_holdings_prices_no_holdings_returns_empty(self) -> None:
        mock_market_data = MagicMock()
        service = PricingService(market_data=mock_market_data)

        prices = service.update_holdings_prices(self.user)

        self.assertEqual(prices, {})
        mock_market_data.get_prices.assert_not_called()

    def test_update_holdings_prices_updates_prices(self) -> None:
        holding = Holding.objects.create(
            account=self.account,
            security=self.security,
            shares=Decimal("10.0"),
        )

        from datetime import datetime

        from django.utils import timezone as tz

        mock_market_data = MagicMock()
        # MarketDataService now returns (price, datetime) tuples
        mock_dt = tz.make_aware(datetime(2024, 1, 1, 12, 0, 0))
        mock_market_data.get_prices.return_value = {"VTI": (Decimal("210.00"), mock_dt)}

        service = PricingService(market_data=mock_market_data)

        result = service.update_holdings_prices(self.user)

        # Check that SecurityPrice was created
        from portfolio.models import SecurityPrice

        price_obj = SecurityPrice.objects.filter(security=self.security).latest("price_datetime")

        # PricingService.update_holdings_prices returns dict[str, Decimal] for backward compatibility
        self.assertEqual(result, {"VTI": Decimal("210.00")})
        self.assertEqual(price_obj.price, Decimal("210.00"))
        self.assertEqual(holding.latest_price, Decimal("210.00"))
        mock_market_data.get_prices.assert_called_once()

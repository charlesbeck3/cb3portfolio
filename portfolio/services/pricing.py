import logging
from decimal import Decimal

from portfolio.models import Holding
from portfolio.services.market_data import MarketDataService
from users.models import CustomUser

logger = logging.getLogger(__name__)


class PricingService:
    """Fetches and updates security prices from external sources."""

    def __init__(self, market_data: MarketDataService | None = None) -> None:
        self._market_data = market_data or MarketDataService()
        logger.debug("Initializing PricingService")

    def update_holdings_prices(self, user: CustomUser) -> dict[str, Decimal]:
        """Fetch current prices and update all holdings for a user.

        Returns a mapping of ticker -> price for reference.
        """

        holdings = Holding.objects.get_for_pricing(user)
        tickers = list({h.security.ticker for h in holdings})

        if not tickers:
            return {}

        price_map = self._market_data.get_prices(tickers)

        for holding in holdings:
            ticker = holding.security.ticker
            if ticker in price_map:
                holding.current_price = price_map[ticker]
                holding.save(update_fields=["current_price"])

        return price_map

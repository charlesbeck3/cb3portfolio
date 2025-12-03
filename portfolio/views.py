from collections import defaultdict
from decimal import Decimal
from typing import Any, DefaultDict, Dict, List, TypedDict, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import AbstractBaseUser
from django.views.generic import TemplateView

from portfolio.models import Account, AssetCategory, Holding
from portfolio.services import PortfolioSummaryService


class AggregatedHolding(TypedDict):
    ticker: str
    name: str
    asset_class: str
    category_code: str
    shares: Decimal
    current_price: Decimal | None
    value: Decimal


class CategoryHoldings(TypedDict):
    holdings: List[AggregatedHolding]
    total: Decimal


def _category_holdings_factory() -> CategoryHoldings:
    return {'holdings': [], 'total': Decimal('0.00')}


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/index.html'

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = cast(AbstractBaseUser, self.request.user)

        # Get summary data
        context['summary'] = PortfolioSummaryService.get_holdings_summary(user)

        # Pass account types for column headers
        context['account_types'] = Account.ACCOUNT_TYPES

        return context


class HoldingsView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/holdings.html'

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = cast(AbstractBaseUser, self.request.user)
        user_pk = cast(int, self.request.user.pk)

        # Update prices first
        PortfolioSummaryService.update_prices(user)

        # Get all holdings for the user
        holdings = Holding.objects.filter(account__user_id=user_pk).select_related(
            'account', 'security', 'security__asset_class'
        )
        # Group holdings by ticker and category

        # First, aggregate by ticker
        ticker_data: Dict[str, AggregatedHolding] = {}
        for holding in holdings:
            ticker = holding.security.ticker
            if ticker not in ticker_data:
                ticker_data[ticker] = {
                    'ticker': ticker,
                    'name': holding.security.name,
                    'asset_class': holding.security.asset_class.name,
                    'category_code': holding.security.asset_class.category_id,
                    'shares': Decimal('0.00'),
                    'current_price': holding.current_price,
                    'value': Decimal('0.00'),
                }

            ticker_data[ticker]['shares'] += holding.shares
            if holding.current_price:
                ticker_data[ticker]['value'] += holding.shares * holding.current_price

        # Now group by category
        categories: DefaultDict[str, CategoryHoldings] = defaultdict(_category_holdings_factory)
        category_labels: Dict[str, str] = {
            category.code: category.label for category in AssetCategory.objects.all()
        }

        for _ticker, data in sorted(ticker_data.items()):
            category_code = data['category_code']
            categories[category_code]['holdings'].append(data)
            categories[category_code]['total'] += data['value']

        # Convert to regular dict and add labels
        context['categories'] = {
            category_labels.get(code, code): data
            for code, data in categories.items()
        }

        # Calculate grand total
        context['grand_total'] = sum(cat['total'] for cat in categories.values())

        return context

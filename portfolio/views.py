from collections import OrderedDict, defaultdict
from decimal import Decimal
from typing import Any, TypedDict, cast

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
    holdings: list[AggregatedHolding]
    total: Decimal


class HoldingsCategory(TypedDict):
    label: str
    total: Decimal
    holdings: list[AggregatedHolding]


class HoldingsGroup(TypedDict):
    label: str
    total: Decimal
    categories: OrderedDict[str, HoldingsCategory]


def _category_holdings_factory() -> CategoryHoldings:
    return {'holdings': [], 'total': Decimal('0.00')}


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/index.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = cast(AbstractBaseUser, self.request.user)

        # Get summary data
        # Get summary data
        context['summary'] = PortfolioSummaryService.get_holdings_summary(user)
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(user)

        # Pass account types for column headers
        context['account_types'] = Account.ACCOUNT_TYPES

        return context


class HoldingsView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/holdings.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
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
        ticker_data: dict[str, AggregatedHolding] = {}
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
        categories: defaultdict[str, CategoryHoldings] = defaultdict(_category_holdings_factory)
        category_qs = AssetCategory.objects.select_related('parent').order_by('sort_order', 'label')
        category_map: dict[str, AssetCategory] = {category.code: category for category in category_qs}
        group_order: list[str] = []
        grouped_category_codes: dict[str, list[str]] = {}
        for category in category_qs:
            group_code = category.parent_id or category.code
            if group_code not in group_order:
                group_order.append(group_code)
            if group_code not in grouped_category_codes:
                grouped_category_codes[group_code] = []
            grouped_category_codes[group_code].append(category.code)

        for _ticker, data in sorted(ticker_data.items()):
            category_code = data['category_code']
            categories[category_code]['holdings'].append(data)
            categories[category_code]['total'] += data['value']

        # Sort holdings within each category by current value (desc) then ticker for stability
        for category_holdings in categories.values():
            category_holdings['holdings'].sort(
                key=lambda holding: (holding['value'], holding['ticker']),
                reverse=True,
            )

        holding_groups: OrderedDict[str, HoldingsGroup] = OrderedDict()
        grand_total = Decimal('0.00')

        for group_code in group_order:
            category_codes = grouped_category_codes.get(group_code, [])
            group_categories: OrderedDict[str, HoldingsCategory] = OrderedDict()
            group_total = Decimal('0.00')

            for category_code in category_codes:
                category_holdings_optional = categories.get(category_code)
                if category_holdings_optional is None or not category_holdings_optional['holdings']:
                    continue

                category_holdings = category_holdings_optional

                category_obj = category_map.get(category_code)
                category_label = category_obj.label if category_obj else category_code

                group_categories[category_code] = {
                    'label': category_label,
                    'total': category_holdings['total'],
                    'holdings': category_holdings['holdings'],
                }
                group_total += category_holdings['total']

            if not group_categories:
                continue

            group_obj = category_map.get(group_code)
            group_label = group_obj.label if group_obj else group_code

            holding_groups[group_code] = {
                'label': group_label,
                'total': group_total,
                'categories': group_categories,
            }
            grand_total += group_total

        context['holding_groups'] = holding_groups
        context['grand_total'] = grand_total

        return context

import logging
from collections import OrderedDict, defaultdict
from decimal import Decimal
from typing import Any

import yfinance as yf

from portfolio.models import Account, AssetCategory, Holding

logger = logging.getLogger(__name__)

CategoryEntry = dict[str, Any]
GroupEntry = dict[str, Any]
SummaryDict = dict[str, Any]


def _asset_class_entry_factory() -> dict[str, Any]:
    return {
        'account_types': defaultdict(Decimal),
        'total': Decimal('0.00'),
    }


def _category_entry_factory() -> CategoryEntry:
    return {
        'asset_classes': defaultdict(_asset_class_entry_factory),
        'total': Decimal('0.00'),
        'account_type_totals': defaultdict(Decimal),
    }


def _group_entry_factory() -> GroupEntry:
    return {
        'label': '',
        'categories': OrderedDict(),
        'total': Decimal('0.00'),
        'account_type_totals': defaultdict(Decimal),
    }


class PortfolioSummaryService:
    @staticmethod
    def update_prices(user: Any) -> None:
        """
        Fetch current prices for all securities held by the user and update Holding.current_price.
        """
        holdings = Holding.objects.filter(account__user=user).select_related('security')
        tickers = list({h.security.ticker for h in holdings})

        if not tickers:
            return

        # Handle cash-equivalent tickers separately - they're always $1.00
        cash_tickers = {'CASH', 'IBOND'}
        cash_holdings = [h for h in holdings if h.security.ticker in cash_tickers]
        for holding in cash_holdings:
            holding.current_price = Decimal('1.00')
            holding.save(update_fields=['current_price'])

        # Remove cash tickers from list to fetch from yfinance
        tickers = [t for t in tickers if t not in cash_tickers]

        if not tickers:
            return

        try:
            # Fetch data for all tickers at once
            data = yf.download(tickers, period="1d", progress=False)['Close']

            # If only one ticker, data is a Series, otherwise DataFrame
            # We need to handle both cases or ensure we access it correctly

            # Create a map of ticker -> price
            price_map = {}
            if len(tickers) == 1:
                # If single ticker, 'data' might be a Series or DataFrame depending on yfinance version/args
                # yfinance 0.2+ usually returns DataFrame with MultiIndex if group_by='ticker' (default is column)
                # But with simple download of 1 ticker, it might be just a DataFrame with columns Open, High, etc.
                # Let's be safe and fetch the last value.
                ticker = tickers[0]
                try:
                    price = data.iloc[-1]
                    # If it's a series (one ticker), price is the value.
                    # If it's a dataframe (multiple columns for one ticker?), we selected 'Close' above.
                    # If 'Close' returned a Series (one ticker), iloc[-1] is the price.
                    val = price.item() if hasattr(price, 'item') else price

                    # Check for NaN
                    if val != val: # NaN check
                         logger.warning(f"Price for {ticker} is NaN")
                    else:
                        price_map[ticker] = Decimal(str(val))
                except Exception:
                    logger.warning(f"Could not extract price for {ticker}")

            else:
                # Multiple tickers, 'data' is a DataFrame where columns are tickers
                # Get the last row (latest prices)
                latest_prices = data.iloc[-1]
                for ticker in tickers:
                    try:
                        price = latest_prices[ticker]
                        val = price.item() if hasattr(price, 'item') else price

                        # Check for NaN
                        if val != val: # NaN check
                             logger.warning(f"Price for {ticker} is NaN")
                             continue

                        price_map[ticker] = Decimal(str(val))
                    except Exception:
                         logger.warning(f"Could not extract price for {ticker}")

            # Update holdings
            for holding in holdings:
                if holding.security.ticker in price_map:
                    holding.current_price = price_map[holding.security.ticker]
                    holding.save(update_fields=['current_price'])

        except Exception as e:
            logger.error(f"Error updating prices: {e}")

    @staticmethod
    def get_holdings_summary(user: Any) -> dict[str, Any]:
        """
        Aggregate holdings by Asset Class (Category) and Account Type.
        Returns a structure suitable for rendering the summary table.
        """
        # Ensure prices are up to date
        PortfolioSummaryService.update_prices(user)

        holdings = Holding.objects.filter(account__user=user).select_related(
            'account',
            'security',
            'security__asset_class',
            'security__asset_class__category',
            'security__asset_class__category__parent',
        )

        # Structure:
        # {
        #   'categories': {
        #       'Category Name': {
        #           'asset_classes': {
        #               'Asset Class Name': {
        #                   'account_types': { 'ROTH_IRA': value, ... },
        #                   'total': value
        #               }
        #           },
        #           'total': value,
        #           'account_type_totals': { 'ROTH_IRA': value, ... }
        #       }
        #   },
        #   'grand_total': value,
        #   'account_type_grand_totals': { 'ROTH_IRA': value, ... }
        # }

        categories = AssetCategory.objects.select_related('parent').all()
        category_labels = {category.code: category.label for category in categories}
        category_group_map: dict[str, str] = {}
        group_labels: dict[str, str] = {}
        for category in categories:
            group = category.parent or category
            category_group_map[category.code] = group.code
            group_labels.setdefault(group.code, group.label)

        categories_summary: defaultdict[str, CategoryEntry] = defaultdict(_category_entry_factory)
        groups_summary: defaultdict[str, GroupEntry] = defaultdict(_group_entry_factory)

        summary: SummaryDict = {
            'categories': categories_summary,
            'groups': groups_summary,
            'grand_total': Decimal('0.00'),
            'account_type_grand_totals': defaultdict(Decimal),
            'account_type_percentages': {},
            'category_labels': category_labels,
            'group_labels': group_labels,
        }

        for holding in holdings:
            if holding.current_price is None:
                continue

            value = holding.shares * holding.current_price

            asset_class = holding.security.asset_class
            category = asset_class.category
            if category is None:
                continue
            category_code = category.code
            asset_class_name = asset_class.name
            account_type_code = holding.account.account_type
            # We use the code for keys, can map to labels in template or here.
            # Let's use codes for keys to be safe and map in template or separate lookup.

            # Update specific asset class entry
            ac_entry = categories_summary[category_code]['asset_classes'][asset_class_name]
            ac_entry['account_types'][account_type_code] += value
            ac_entry['total'] += value

            # Update category totals
            cat_entry = categories_summary[category_code]
            cat_entry['total'] += value
            cat_entry['account_type_totals'][account_type_code] += value

            group_code = category_group_map.get(category_code, category_code)
            group_entry = groups_summary[group_code]
            if not group_entry['label']:
                group_entry['label'] = group_labels.get(group_code, category.label if category.parent else category.label)
            group_entry['total'] += value
            group_entry['account_type_totals'][account_type_code] += value

            # Update grand totals
            summary['grand_total'] += value
            summary['account_type_grand_totals'][account_type_code] += value

        # Convert defaultdicts to dicts for template iteration
        # Django templates can have issues with defaultdicts (accessing .items lookup)

        # Sort asset classes within each category and categories by total value (descending)
        for _category_code, category_data in categories_summary.items():
            asset_classes = category_data['asset_classes']
            sorted_asset_classes = sorted(
                asset_classes.items(), key=lambda item: item[1]['total'], reverse=True
            )
            category_data['asset_classes'] = OrderedDict(sorted_asset_classes)

        sorted_categories = sorted(
            categories_summary.items(), key=lambda item: item[1]['total'], reverse=True
        )
        summary['categories'] = OrderedDict(sorted_categories)

        # Assign sorted categories to their groups and sort groups
        for category_code, category_data in summary['categories'].items():
            group_code = category_group_map.get(category_code, category_code)
            group_entry = groups_summary[group_code]
            group_entry['categories'][category_code] = category_data

        sorted_groups = sorted(
            groups_summary.items(), key=lambda item: item[1]['total'], reverse=True
        )
        summary['groups'] = OrderedDict(sorted_groups)

        grand_total = summary['grand_total']
        account_type_percentages: dict[str, Decimal] = {}
        if grand_total > 0:
            for code, value in summary['account_type_grand_totals'].items():
                account_type_percentages[code] = (value / grand_total) * Decimal('100')
        else:
            for code in summary['account_type_grand_totals']:
                account_type_percentages[code] = Decimal('0.00')

        summary['account_type_percentages'] = account_type_percentages

        # Deep convert function
        def default_to_regular(d: Any) -> Any:
            if isinstance(d, dict):
                d = {k: default_to_regular(v) for k, v in d.items()}
            return d

        return default_to_regular(summary)

    @staticmethod
    def get_account_summary(user: Any) -> dict[str, Any]:
        """
        Get summary of accounts grouped by type (Retirement vs Investments).
        """
        # Ensure prices are up to date
        PortfolioSummaryService.update_prices(user)

        accounts = Account.objects.filter(user=user).prefetch_related('holdings')
        
        # Define groups
        groups = {
            'Retirement': {'label': 'Retirement', 'total': Decimal('0.00'), 'accounts': []},
            'Investments': {'label': 'Investments', 'total': Decimal('0.00'), 'accounts': []},
            'Cash': {'label': 'Cash', 'total': Decimal('0.00'), 'accounts': []},
        }
        
        # Mapping account types to groups
        type_map = {
            'ROTH_IRA': 'Retirement',
            'TRADITIONAL_IRA': 'Retirement',
            '401K': 'Retirement',
            'TAXABLE': 'Investments',
        }

        grand_total = Decimal('0.00')

        for account in accounts:
            # Calculate account total
            account_total = Decimal('0.00')
            for holding in account.holdings.all():
                if holding.current_price:
                    account_total += holding.shares * holding.current_price
            
            group_name = type_map.get(account.account_type, 'Investments')
            
            # Check if it's a cash account (heuristic based on name or holdings?)
            # For now, rely on type map.
            
            groups[group_name]['accounts'].append({
                'id': account.id,
                'name': account.name,
                'institution': account.institution,
                'total': account_total,
                'account_type': account.account_type,
            })
            groups[group_name]['total'] += account_total
            grand_total += account_total

        # Remove empty groups and sort by total value descending
        active_groups = {k: v for k, v in groups.items() if v['accounts']}
        sorted_groups = dict(sorted(active_groups.items(), key=lambda item: item[1]['total'], reverse=True))
        
        return {
            'groups': sorted_groups,
            'grand_total': grand_total,
        }

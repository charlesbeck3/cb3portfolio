import logging
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import yfinance as yf

from portfolio.models import Account, AssetCategory, Holding, TargetAllocation

logger = logging.getLogger(__name__)


@dataclass
class AccountTypeData:
    current: Decimal = Decimal('0.00')
    target: Decimal = Decimal('0.00')
    variance: Decimal = Decimal('0.00')


@dataclass
class AssetClassEntry:
    account_types: dict[str, AccountTypeData] = field(default_factory=lambda: defaultdict(AccountTypeData))
    total: Decimal = Decimal('0.00')


@dataclass
class CategoryEntry:
    asset_classes: dict[str, AssetClassEntry] = field(default_factory=lambda: defaultdict(AssetClassEntry))
    total: Decimal = Decimal('0.00')
    account_type_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_target_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_variance_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))


@dataclass
class GroupEntry:
    label: str = ''
    categories: OrderedDict[str, CategoryEntry] = field(default_factory=OrderedDict)
    total: Decimal = Decimal('0.00')
    account_type_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_target_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_variance_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))


@dataclass
class PortfolioSummary:
    categories: dict[str, CategoryEntry] = field(default_factory=lambda: defaultdict(CategoryEntry))
    groups: dict[str, GroupEntry] = field(default_factory=lambda: defaultdict(GroupEntry))
    grand_total: Decimal = Decimal('0.00')
    grand_target_total: Decimal = Decimal('0.00')
    grand_variance_total: Decimal = Decimal('0.00')
    account_type_grand_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_grand_target_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_grand_variance_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_percentages: dict[str, Decimal] = field(default_factory=dict)
    category_labels: dict[str, str] = field(default_factory=dict)
    group_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class AggregatedHolding:
    ticker: str
    name: str
    asset_class: str
    category_code: str
    shares: Decimal = Decimal('0.00')
    current_price: Decimal | None = None
    value: Decimal = Decimal('0.00')


@dataclass
class HoldingsCategory:
    label: str
    total: Decimal = Decimal('0.00')
    holdings: list[AggregatedHolding] = field(default_factory=list)


@dataclass
class HoldingsGroup:
    label: str
    total: Decimal = Decimal('0.00')
    categories: OrderedDict[str, HoldingsCategory] = field(default_factory=OrderedDict)


@dataclass
class HoldingsSummary:
    grand_total: Decimal = Decimal('0.00')
    holding_groups: OrderedDict[str, HoldingsGroup] = field(default_factory=OrderedDict)


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
    def get_holdings_summary(user: Any) -> PortfolioSummary:
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

        categories = AssetCategory.objects.select_related('parent').all()
        category_labels = {category.code: category.label for category in categories}
        category_group_map: dict[str, str] = {}
        group_labels: dict[str, str] = {}
        for category in categories:
            group = category.parent or category
            category_group_map[category.code] = group.code
            group_labels.setdefault(group.code, group.label)

        summary = PortfolioSummary(
            category_labels=category_labels,
            group_labels=group_labels,
        )

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

            # Update specific asset class entry
            ac_entry = summary.categories[category_code].asset_classes[asset_class_name]
            ac_entry.account_types[account_type_code].current += value
            ac_entry.total += value

            # Update category totals
            cat_entry = summary.categories[category_code]
            cat_entry.total += value
            cat_entry.account_type_totals[account_type_code] += value

            group_code = category_group_map.get(category_code, category_code)
            group_entry = summary.groups[group_code]
            if not group_entry.label:
                group_entry.label = group_labels.get(group_code, category.label if category.parent else category.label)
            group_entry.total += value
            group_entry.account_type_totals[account_type_code] += value

            # Update grand totals
            summary.grand_total += value
            summary.account_type_grand_totals[account_type_code] += value

        # Fetch target allocations and calculate target/variance values
        target_allocations = TargetAllocation.objects.filter(user=user).select_related('asset_class')
        target_lookup: dict[tuple[str, str], Decimal] = {}
        for target in target_allocations:
            key = (target.account_type, target.asset_class.name)
            target_lookup[key] = target.target_pct

        # Calculate target dollar amounts and variances
        for category_code, category_data in summary.categories.items():
            for asset_class_name, asset_class_data in category_data.asset_classes.items():
                for account_type_code, account_data in asset_class_data.account_types.items():
                    # Get target percentage (default to 0 if not found)
                    target_pct = target_lookup.get((account_type_code, asset_class_name), Decimal('0.00'))

                    # Calculate target dollar amount
                    account_type_total = summary.account_type_grand_totals.get(account_type_code, Decimal('0.00'))
                    target_dollars = account_type_total * (target_pct / Decimal('100'))

                    # Calculate variance
                    current_dollars = account_data.current
                    variance_dollars = current_dollars - target_dollars

                    # Update the account data
                    account_data.target = target_dollars
                    account_data.variance = variance_dollars

                    # Update category totals
                    category_data.account_type_target_totals[account_type_code] += target_dollars
                    category_data.account_type_variance_totals[account_type_code] += variance_dollars

                    # Update group totals
                    group_code = category_group_map.get(category_code, category_code)
                    group_entry = summary.groups[group_code]
                    group_entry.account_type_target_totals[account_type_code] += target_dollars
                    group_entry.account_type_variance_totals[account_type_code] += variance_dollars

                    # Update grand totals
                    summary.account_type_grand_target_totals[account_type_code] += target_dollars
                    summary.account_type_grand_variance_totals[account_type_code] += variance_dollars
                    summary.grand_target_total += target_dollars
                    summary.grand_variance_total += variance_dollars

        # Sort asset classes within each category and categories by total value (descending)
        for _category_code, category_data in summary.categories.items():
            asset_classes = category_data.asset_classes
            sorted_asset_classes = sorted(
                asset_classes.items(), key=lambda item: item[1].total, reverse=True
            )
            category_data.asset_classes = OrderedDict(sorted_asset_classes)

        sorted_categories = sorted(
            summary.categories.items(), key=lambda item: item[1].total, reverse=True
        )
        summary.categories = OrderedDict(sorted_categories)

        # Assign sorted categories to their groups and sort groups
        for category_code, category_data in summary.categories.items():
            group_code = category_group_map.get(category_code, category_code)
            group_entry = summary.groups[group_code]
            group_entry.categories[category_code] = category_data

        sorted_groups = sorted(
            summary.groups.items(), key=lambda item: item[1].total, reverse=True
        )
        summary.groups = OrderedDict(sorted_groups)

        grand_total = summary.grand_total
        account_type_percentages: dict[str, Decimal] = {}
        if grand_total > 0:
            for code, value in summary.account_type_grand_totals.items():
                account_type_percentages[code] = (value / grand_total) * Decimal('100')
        else:
            for code in summary.account_type_grand_totals:
                account_type_percentages[code] = Decimal('0.00')

        summary.account_type_percentages = account_type_percentages

        return summary

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

    @staticmethod
    def get_holdings_by_category(user: Any) -> dict[str, Any]:
        """
        Get all holdings grouped by category and group, sorted by value.
        """
        # Ensure prices are up to date
        PortfolioSummaryService.update_prices(user)

        holdings = Holding.objects.filter(account__user=user).select_related(
            'account', 'security', 'security__asset_class'
        )

        # First, aggregate by ticker
        ticker_data: dict[str, AggregatedHolding] = {}
        for holding in holdings:
            ticker = holding.security.ticker
            if ticker not in ticker_data:
                ticker_data[ticker] = AggregatedHolding(
                    ticker=ticker,
                    name=holding.security.name,
                    asset_class=holding.security.asset_class.name,
                    category_code=holding.security.asset_class.category_id,
                    current_price=holding.current_price,
                )

            ticker_data[ticker].shares += holding.shares
            if holding.current_price:
                ticker_data[ticker].value += holding.shares * holding.current_price

        # Now group by category
        categories: defaultdict[str, HoldingsCategory] = defaultdict(
            lambda: HoldingsCategory(label='', holdings=[])
        )
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
            category_code = data.category_code
            if not categories[category_code].label:
                 cat_obj = category_map.get(category_code)
                 categories[category_code].label = cat_obj.label if cat_obj else category_code
            
            categories[category_code].holdings.append(data)
            categories[category_code].total += data.value

        # Sort holdings within each category by current value (desc) then ticker for stability
        for category_holdings in categories.values():
            category_holdings.holdings.sort(
                key=lambda holding: (holding.value, holding.ticker),
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
                if category_holdings_optional is None or not category_holdings_optional.holdings:
                    continue

                category_holdings = category_holdings_optional
                
                # Ensure label is set (might not be if no holdings populated it yet, but we skip empty ones)
                if not category_holdings.label:
                     cat_obj = category_map.get(category_code)
                     category_holdings.label = cat_obj.label if cat_obj else category_code

                group_categories[category_code] = category_holdings
                group_total += category_holdings.total

            if not group_categories:
                continue

            group_obj = category_map.get(group_code)
            group_label = group_obj.label if group_obj else group_code

            holding_groups[group_code] = HoldingsGroup(
                label=group_label,
                total=group_total,
                categories=group_categories,
            )
            grand_total += group_total

        return {
            'holding_groups': holding_groups,
            'grand_total': grand_total,
        }

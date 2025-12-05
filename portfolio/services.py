import logging
from collections import OrderedDict, defaultdict
from decimal import Decimal
from typing import Any

from portfolio.market_data import MarketDataService
from portfolio.models import Account, AssetCategory, Holding, TargetAllocation
from portfolio.structs import (
    AggregatedHolding,
    HoldingsCategory,
    HoldingsGroup,
    PortfolioSummary,
)

logger = logging.getLogger(__name__)


class PortfolioSummaryService:
    @staticmethod
    def update_prices(user: Any) -> None:
        """
        Fetch current prices for all securities held by the user and update Holding.current_price.
        """
        holdings = Holding.objects.get_for_pricing(user)
        tickers = list({h.security.ticker for h in holdings})

        if not tickers:
            return

        price_map = MarketDataService.get_prices(tickers)

        # Update holdings
        for holding in holdings:
            if holding.security.ticker in price_map:
                holding.current_price = price_map[holding.security.ticker]
                holding.save(update_fields=['current_price'])

    @staticmethod
    def get_holdings_summary(user: Any) -> PortfolioSummary:
        """
        Aggregate holdings by Asset Class (Category) and Account Type.
        Returns a structure suitable for rendering the summary table.
        """
        # Ensure prices are up to date
        PortfolioSummaryService.update_prices(user)

        # 1. Fetch Data & Initialize Structure
        holdings = Holding.objects.get_for_summary(user)
        categories = AssetCategory.objects.select_related('parent').all()

        category_labels, category_group_map, group_labels = PortfolioSummaryService._build_category_maps(categories)

        summary = PortfolioSummary(
            category_labels=category_labels,
            group_labels=group_labels,
        )

        # 2. Aggregate Holdings into Summary
        PortfolioSummaryService._aggregate_holdings(summary, holdings, category_group_map, group_labels)

        # 3. Calculate Targets and Variances
        PortfolioSummaryService._calculate_targets_and_variances(
            user, summary, category_group_map
        )

        # 4. Sort and Organize
        PortfolioSummaryService._sort_and_organize_summary(summary, category_group_map)

        return summary

    @staticmethod
    def _build_category_maps(categories: Any) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        category_labels = {category.code: category.label for category in categories}
        category_group_map: dict[str, str] = {}
        group_labels: dict[str, str] = {}
        for category in categories:
            group = category.parent or category
            category_group_map[category.code] = group.code
            group_labels.setdefault(group.code, group.label)
        return category_labels, category_group_map, group_labels

    @staticmethod
    def _aggregate_holdings(
        summary: PortfolioSummary,
        holdings: Any,
        category_group_map: dict[str, str],
        group_labels: dict[str, str]
    ) -> None:
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
            account_type_code = holding.account.account_type.code

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
                # Fallback label logic if not set
                group_entry.label = group_labels.get(group_code, group_code)

            group_entry.total += value
            group_entry.account_type_totals[account_type_code] += value

            # Update grand totals
            summary.grand_total += value
            summary.account_type_grand_totals[account_type_code] += value

    @staticmethod
    def _calculate_targets_and_variances(
        user: Any,
        summary: PortfolioSummary,
        category_group_map: dict[str, str],
    ) -> None:
        target_allocations = TargetAllocation.objects.get_for_user(user)
        target_lookup: dict[tuple[str, str], Decimal] = {}
        for target in target_allocations:
            key = (target.account_type.code, target.asset_class.name)
            target_lookup[key] = target.target_pct

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

                    # Update asset class totals
                    asset_class_data.target_total += target_dollars
                    asset_class_data.variance_total += variance_dollars

                    # Update category totals
                    category_data.account_type_target_totals[account_type_code] += target_dollars
                    category_data.account_type_variance_totals[account_type_code] += variance_dollars
                    category_data.target_total += target_dollars
                    category_data.variance_total += variance_dollars

                    # Update group totals
                    group_code = category_group_map.get(category_code, category_code)
                    group_entry = summary.groups[group_code]
                    group_entry.account_type_target_totals[account_type_code] += target_dollars
                    group_entry.account_type_variance_totals[account_type_code] += variance_dollars
                    group_entry.target_total += target_dollars
                    group_entry.variance_total += variance_dollars

                    # Update grand totals
                    summary.account_type_grand_target_totals[account_type_code] += target_dollars
                    summary.account_type_grand_variance_totals[account_type_code] += variance_dollars
                    summary.grand_target_total += target_dollars
                    summary.grand_variance_total += variance_dollars

    @staticmethod
    def _sort_and_organize_summary(summary: PortfolioSummary, category_group_map: dict[str, str]) -> None:
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

    @staticmethod
    def get_account_summary(user: Any) -> dict[str, Any]:
        """
        Get summary of accounts grouped by AccountGroup.
        Includes aggregate absolute deviation from target allocation for each account.
        """
        # Ensure prices are up to date
        PortfolioSummaryService.update_prices(user)

        # Prefetch data using Manager
        accounts = Account.objects.get_summary_data(user)

        # 1. Fetch all targets for this user and map by account_type_code -> asset_class_name
        targets = TargetAllocation.objects.get_for_user(user)
        # Map: account_type_code -> asset_class_name -> target_pct
        target_map: dict[str, dict[str, Decimal]] = defaultdict(dict)
        for t in targets:
            # t.account_type is now a foreign key object
            target_map[t.account_type.code][t.asset_class.name] = t.target_pct

        # Initialize groups dynamically from AccountGroup model
        # We need an OrderedDict to maintain display order
        # Key: group_name, Value: {label, total, accounts}

        # Load all groups ordered by sort_order
        from .models import AccountGroup  # Delayed import to avoid circular dependency if any

        all_groups = AccountGroup.objects.all()
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for g in all_groups:
            groups[g.name] = {
                'label': g.name,
                'total': Decimal('0.00'),
                'accounts': []
            }

        # Add 'Other' group for unassigned accounts
        if 'Other' not in groups:
             groups['Other'] = {
                'label': 'Other',
                'total': Decimal('0.00'),
                'accounts': []
            }

        grand_total = Decimal('0.00')

        for account in accounts:
            account_total = Decimal('0.00')
            # Group holdings by asset class to compare with targets
            # Map: asset_class_name -> current_value
            holdings_by_ac: dict[str, Decimal] = defaultdict(Decimal)

            for holding in account.holdings.all():
                if holding.current_price:
                    val = holding.shares * holding.current_price
                    account_total += val
                    holdings_by_ac[holding.security.asset_class.name] += val

            # Calculate Absolute Deviation
            # Deviation = Sum(Abs(Actual_Value - Target_Value)) for each asset class
            # We need to consider all asset classes that have EITHER a holding OR a target.

            # account.account_type is the object, get 'code' for lookup
            account_targets = target_map.get(account.account_type.code, {})
            all_asset_classes = set(holdings_by_ac.keys()) | set(account_targets.keys())

            absolute_deviation = Decimal('0.00')
            absolute_deviation_pct = Decimal('0.00')

            if account_total > 0:
                for ac_name in all_asset_classes:
                    actual_val = holdings_by_ac.get(ac_name, Decimal('0.00'))
                    target_pct = account_targets.get(ac_name, Decimal('0.00'))
                    target_val = account_total * (target_pct / Decimal('100.00'))
                    absolute_deviation += abs(actual_val - target_val)

                absolute_deviation_pct = (absolute_deviation / account_total) * Decimal('100.00')

            # Determine group
            # Use account.account_type.group
            group_name = 'Other'
            if account.account_type.group:
                group_name = account.account_type.group.name

            # If for some reason the group exists on the account but wasn't in our initial fetch (race condition?),
            # fallback to Other or create it dynamically (safer to use Other for now)
            if group_name not in groups:
                 group_name = 'Other'

            groups[group_name]['accounts'].append({
                'id': account.id,
                'name': account.name,
                'institution': account.institution.name if account.institution else 'N/A',
                'total': account_total,
                'absolute_deviation': absolute_deviation,
                'absolute_deviation_pct': absolute_deviation_pct
            })
            groups[group_name]['total'] += account_total
            grand_total += account_total

        # Filter out "Other" if empty
        if 'Other' in groups and not groups['Other']['accounts']:
            del groups['Other']

        # Filter out any other groups that might be empty (e.g., from AccountGroup but no accounts assigned)
        # This ensures we only show groups that actually contain accounts.
        groups_with_accounts = {k: v for k, v in groups.items() if v['accounts']}

        # Sort accounts within each group
        for group_data in groups_with_accounts.values():
            group_data['accounts'].sort(key=lambda x: x['total'], reverse=True)

        # Sort the groups themselves by their total value
        sorted_groups = dict(sorted(groups_with_accounts.items(), key=lambda item: item[1]['total'], reverse=True))

        return {
            'grand_total': grand_total,
            'groups': sorted_groups,
        }

    @staticmethod
    def get_holdings_by_category(user: Any, account_id: int | None = None) -> dict[str, Any]:
        """
        Get all holdings grouped by category and group, sorted by value.
        Optionally filter by account_id.
        Includes target allocation, current allocation, and variance calculations.
        """
        # Ensure prices are up to date
        PortfolioSummaryService.update_prices(user)

        # Fetch base data
        holdings_qs = Holding.objects.get_for_category_view(user)
        if account_id:
            holdings_qs = holdings_qs.filter(account_id=account_id)

        target_allocations = TargetAllocation.objects.get_for_user(user)

        # --- PRE-CALCULATION PHASE ---

        # Map targets: (account_type_code, asset_class_id) -> target_pct
        target_map: dict[tuple[str, int], Decimal] = {}
        for ta in target_allocations:
            target_map[(ta.account_type.code, ta.asset_class_id)] = ta.target_pct

        # Calculate Account Totals and Security Counts per Asset Class per Account
        account_totals: dict[int, Decimal] = defaultdict(Decimal)
        # account_id -> asset_class_id -> set of security tickers
        account_ac_security_counts: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
        # Account-level security count mapping since we might filter by account_id but need context
        # Actually, if we filter by account_id, we only care about that account's context.

        # We need to iterate ALL holdings to build the account stats first, even if we are filtering?
        # No, if we filter by account_id, we only show data for that account.

        for holding in holdings_qs:
            val = Decimal('0.00')
            if holding.current_price:
                 val = holding.shares * holding.current_price

            account_totals[holding.account_id] += val
            account_ac_security_counts[holding.account_id][holding.security.asset_class_id].add(holding.security.ticker)


        # --- AGGREGATION PHASE ---

        ticker_data: dict[str, AggregatedHolding] = {}
        grand_total_value = Decimal('0.00')

        for holding in holdings_qs:
            ticker = holding.security.ticker
            current_val = Decimal('0.00')
            if holding.current_price:
                current_val = holding.shares * holding.current_price

            grand_total_value += current_val

            # Determine Target Value for this specific holding instance
            # Target for Asset Class in this Account
            # holding.account.account_type is the model instance, use .code
            ac_target_pct = target_map.get((holding.account.account_type.code, holding.security.asset_class_id), Decimal('0.00'))

            # Number of securities in this asset class held in this account
            num_securities = len(account_ac_security_counts[holding.account_id][holding.security.asset_class_id])

            # Allocate target evenly among securities
            # If num_securities is 0 (shouldn't happen here), handle division by zero
            security_target_pct = ac_target_pct / Decimal(num_securities) if num_securities > 0 else Decimal('0.00')

            # Dollar Target for this holding
            account_total = account_totals[holding.account_id]
            holding_target_value = account_total * (security_target_pct / Decimal('100.00'))

            # Target Shares
            # If price is 0 or None, we can't calculate target shares reasonably.
            holding_target_shares = Decimal('0.00')
            if holding.current_price and holding.current_price > 0:
                 holding_target_shares = holding_target_value / holding.current_price


            if ticker not in ticker_data:
                ticker_data[ticker] = AggregatedHolding(
                    ticker=ticker,
                    name=holding.security.name,
                    asset_class=holding.security.asset_class.name,
                    category_code=holding.security.asset_class.category_id,
                    current_price=holding.current_price,
                )

            ticker_data[ticker].shares += holding.shares
            ticker_data[ticker].value += current_val
            ticker_data[ticker].target_value += holding_target_value
            ticker_data[ticker].target_shares += holding_target_shares

        # --- FINAL METRICS CALCULATION ---

        for holding_data in ticker_data.values():
            # Current Allocation %
            if grand_total_value > 0:
                holding_data.current_allocation = (holding_data.value / grand_total_value) * Decimal('100.00')
                holding_data.target_allocation = (holding_data.target_value / grand_total_value) * Decimal('100.00')

            # Variances
            holding_data.value_variance = holding_data.value - holding_data.target_value
            holding_data.shares_variance = holding_data.shares - holding_data.target_shares
            holding_data.allocation_variance = holding_data.current_allocation - holding_data.target_allocation


        # --- GROUPING ---

        # Now group by category (existing logic)
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
            categories[category_code].total_target_value += data.target_value
            categories[category_code].total_value_variance += data.value_variance
            categories[category_code].total_current_allocation += data.current_allocation
            categories[category_code].total_target_allocation += data.target_allocation
            categories[category_code].total_allocation_variance += data.allocation_variance

        # Sort holdings within each category by current value (desc) then ticker for stability
        for category_holdings in categories.values():
            category_holdings.holdings.sort(
                key=lambda holding: (holding.value, holding.ticker),
                reverse=True,
            )

        holding_groups: OrderedDict[str, HoldingsGroup] = OrderedDict()
        grand_target_value = Decimal('0.00')
        grand_value_variance = Decimal('0.00')
        grand_current_allocation = Decimal('0.00')
        grand_target_allocation = Decimal('0.00')
        grand_allocation_variance = Decimal('0.00')

        for group_code in group_order:
            category_codes = grouped_category_codes.get(group_code, [])
            group_categories: OrderedDict[str, HoldingsCategory] = OrderedDict()
            group_total = Decimal('0.00')
            group_target_value = Decimal('0.00')
            group_value_variance = Decimal('0.00')
            group_current_allocation = Decimal('0.00')
            group_target_allocation = Decimal('0.00')
            group_allocation_variance = Decimal('0.00')

            for category_code in category_codes:
                category_holdings_optional = categories.get(category_code)
                if category_holdings_optional is None or not category_holdings_optional.holdings:
                    continue

                category_holdings = category_holdings_optional

                # Ensure label is set
                if not category_holdings.label:
                     cat_obj = category_map.get(category_code)
                     category_holdings.label = cat_obj.label if cat_obj else category_code

                group_categories[category_code] = category_holdings
                group_total += category_holdings.total
                group_target_value += category_holdings.total_target_value
                group_value_variance += category_holdings.total_value_variance
                group_current_allocation += category_holdings.total_current_allocation
                group_target_allocation += category_holdings.total_target_allocation
                group_allocation_variance += category_holdings.total_allocation_variance

            if not group_categories:
                continue

            group_obj = category_map.get(group_code)
            group_label = group_obj.label if group_obj else group_code

            holding_groups[group_code] = HoldingsGroup(
                label=group_label,
                total=group_total,
                total_target_value=group_target_value,
                total_value_variance=group_value_variance,
                total_current_allocation=group_current_allocation,
                total_target_allocation=group_target_allocation,
                total_allocation_variance=group_allocation_variance,
                categories=group_categories,
            )
            grand_target_value += group_target_value
            grand_value_variance += group_value_variance
            grand_current_allocation += group_current_allocation
            grand_target_allocation += group_target_allocation
            grand_allocation_variance += group_allocation_variance

        return {
            'holding_groups': holding_groups,
            'grand_total': grand_total_value,
            'grand_target_value': grand_target_value,
            'grand_value_variance': grand_value_variance,
            'grand_current_allocation': grand_current_allocation,
            'grand_target_allocation': grand_target_allocation,
            'grand_allocation_variance': grand_allocation_variance,
        }

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
                holding.save(update_fields=["current_price"])

    @staticmethod
    def get_effective_targets(user: Any) -> dict[int, dict[str, Decimal]]:
        """
        Get the effective target allocation percentage for each account and asset class.
        Returns: {account_id: {asset_class_name: target_pct}}
        Logic:
           1. Start with Account Type defaults for all Asset Classes.
           2. Overlay Account-specific overrides.
        """
        # Fetch all targets
        targets = TargetAllocation.objects.filter(user=user).select_related(
            "account_type", "asset_class", "account"
        )

        # 1. Build Type Defaults: {account_type_id: {asset_class_name: pct}}
        type_defaults: dict[int, dict[str, Decimal]] = defaultdict(dict)
        # 2. Build Account Overrides: {account_id: {asset_class_name: pct}}
        account_overrides: dict[int, dict[str, Decimal]] = defaultdict(dict)

        for t in targets:
            ac_name = t.asset_class.name
            if t.account_id:
                account_overrides[t.account_id][ac_name] = t.target_pct
            else:
                type_defaults[t.account_type_id][ac_name] = t.target_pct

        # Fetch all User Accounts to resolve effective targets for each
        accounts = Account.objects.filter(user=user).select_related("account_type")

        effective_targets: dict[int, dict[str, Decimal]] = {}

        for account in accounts:
            # Check if this account has specific overrides
            overrides = account_overrides.get(account.id, {})

            if overrides:
                # STRATEGY CHANGE: If ANY override exists for an account, ignore ALL defaults.
                # The account follows a purely custom strategy.
                effective_targets[account.id] = overrides.copy()
            else:
                # Fallback to Account Type defaults
                defaults = type_defaults.get(account.account_type_id, {}).copy()
                effective_targets[account.id] = defaults

        return effective_targets

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
        categories = AssetCategory.objects.select_related("parent").all()
        # Ensure we have all Asset Classes in the summary structure initialized
        # (Pass 2 may skip this if we trust holdings cover it, but for targets we need empty slots?)
        # Currently the summary structure is built dynamically by asset class name encounter?
        # See _aggregate_holdings update...

        category_labels, category_group_map, group_labels = (
            PortfolioSummaryService._build_category_maps(categories)
        )

        summary = PortfolioSummary(
            category_labels=category_labels,
            group_labels=group_labels,
        )

        # Pre-initialize asset classes in summary so targets can be filled even if no holdings?
        # Fetching all asset classes:
        from .models import AssetClass

        all_asset_classes = AssetClass.objects.select_related("category").all()
        for ac in all_asset_classes:
            cat_code = ac.category.code
            # Ensure category exists in summary
            if cat_code not in summary.categories:
                # Initialize category... (done by defaultdict in PortfolioSummary but we need to ensure labels)
                pass
            # Initialize asset class slot
            ac_entry = summary.categories[cat_code].asset_classes[ac.name]
            ac_entry.id = ac.id

        # 2. Aggregate Holdings into Summary + Track Account Totals
        account_totals: dict[int, Decimal] = defaultdict(Decimal)
        account_type_map: dict[int, str] = {}

        PortfolioSummaryService._aggregate_holdings(
            summary, holdings, category_group_map, group_labels, account_totals, account_type_map
        )

        # 3. Calculate Targets and Variances (Bottom-Up)
        PortfolioSummaryService._calculate_targets_and_variances(
            user, summary, category_group_map, account_totals, account_type_map
        )

        # 4. Calculate Percentages (for all account type aggregations)
        PortfolioSummaryService._calculate_percentages(summary)

        # 5. Sort and Organize
        PortfolioSummaryService._sort_and_organize_summary(summary, category_group_map)

        return summary

    @staticmethod
    def _build_category_maps(
        categories: Any,
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
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
        group_labels: dict[str, str],
        account_totals: dict[int, Decimal],
        account_type_map: dict[int, str],
    ) -> None:
        for holding in holdings:
            if holding.current_price is None:
                continue

            value = holding.shares * holding.current_price

            # Track Account Totals for Target Calculation
            account_totals[holding.account_id] += value
            if holding.account_id not in account_type_map:
                account_type_map[holding.account_id] = holding.account.account_type.code

            asset_class = holding.security.asset_class
            category = asset_class.category
            if category is None:
                continue
            category_code = category.code
            asset_class_name = asset_class.name
            account_type_code = holding.account.account_type.code

            # Update specific asset class entry
            ac_entry = summary.categories[category_code].asset_classes[asset_class_name]
            if ac_entry.id is None:
                ac_entry.id = asset_class.id
            ac_entry.account_types[account_type_code].current += value
            ac_entry.total += value

            # Update category totals
            cat_entry = summary.categories[category_code]
            cat_entry.total += value
            cat_entry.account_type_totals[account_type_code] += value
            cat_entry.account_totals[holding.account_id] += value

            group_code = category_group_map.get(category_code, category_code)
            group_entry = summary.groups[group_code]
            if not group_entry.label:
                # Fallback label logic if not set
                group_entry.label = group_labels.get(group_code, group_code)

            group_entry.total += value
            group_entry.account_type_totals[account_type_code] += value
            group_entry.account_totals[holding.account_id] += value

            # Update grand totals
            summary.grand_total += value
            summary.account_type_grand_totals[account_type_code] += value
            summary.account_grand_totals[holding.account_id] += value

    @staticmethod
    def _calculate_targets_and_variances(
        user: Any,
        summary: PortfolioSummary,
        category_group_map: dict[str, str],
        account_totals: dict[int, Decimal],
        account_type_map: dict[int, str],  # account_id -> account_type_code
    ) -> None:
        # 1. Get Effective Targets per Account
        # Map: account_id -> asset_class_name -> target_pct
        effective_targets = PortfolioSummaryService.get_effective_targets(user)

        # 2. Iterate through all accounts to calculate target dollars
        # These will be aggregated into the summary structure

        # We need a reverse map of asset class name -> category/group info to update the right buckets
        # Or we can just iterate the effective targets if we know they cover all asset classes?
        # Better: iterate through accounts, then iterate through their target map.

        # We also need to clear existing target/variance fields in summary?
        # They are initialized to 0 in structs.py so we should be fine accumulating.

        # However, we must ensure we cover ALL asset classes for an account, even if target is 0?
        # Actually, if target is 0, target_dollars is 0.
        # But we need to ensure we calculate variance for asset classes that have HOLDINGS but NO TARGET.
        # The current implementation calculates variance based on (Current - Target).
        # We need to sum up Target Dollars from this bottom-up approach.
        # Then, after summing all Target Dollars, `variance` can be calculated as `current - target`.

        # So providing we correctly sum all target dollars into the `summary` structure,
        # we can then do a pass to calculate variances?
        # OR we can calculate variances at the end.

        # The `summary` structure already has `current` populated.
        # We just need to populate `target`.

        # 2a. Calculate Target Dollars
        for account_id, ac_targets in effective_targets.items():
            account_total = account_totals.get(account_id, Decimal("0.00"))
            if account_total == 0:
                continue

            at_code = account_type_map.get(account_id)
            if not at_code:
                continue

            for asset_class_name, target_pct in ac_targets.items():
                target_dollars = account_total * (target_pct / Decimal("100.00"))

                # Where does this asset class belong?
                # We need to find its category code.
                # Use a helper lookup or search?
                # Since we don't have a direct map here, let's find it in the summary structure.
                # This is slightly inefficient but safe.

                # Optimization: Build AC -> Category map once
                # Actually we can do this in the outer scope or pass it in.
                # Let's try to find it in summary.

                found = False
                for cat_code, cat_data in summary.categories.items():
                    if asset_class_name in cat_data.asset_classes:
                        # Update Asset Class
                        ac_data = cat_data.asset_classes[asset_class_name]
                        ac_data.account_types[at_code].target += target_dollars
                        ac_data.target_total += target_dollars

                        # Track per-account, per-asset-class target dollars
                        if ac_data.id is not None:
                            summary.account_asset_targets[account_id][ac_data.id] += target_dollars

                        # Update Category
                        cat_data.account_type_target_totals[at_code] += target_dollars
                        cat_data.account_target_totals[account_id] += target_dollars
                        cat_data.target_total += target_dollars

                        # Update Group
                        group_code = category_group_map.get(cat_code, cat_code)
                        group_entry = summary.groups[group_code]
                        group_entry.account_type_target_totals[at_code] += target_dollars
                        group_entry.account_target_totals[account_id] += target_dollars
                        group_entry.target_total += target_dollars

                        # Update Grand Total
                        summary.account_type_grand_target_totals[at_code] += target_dollars
                        summary.account_grand_target_totals[account_id] += target_dollars
                        summary.grand_target_total += target_dollars

                        found = True
                        break

                if not found:
                    # Asset class might exist in targets but not in current summary (no holdings)?
                    # If so, we should theoretically show it, but the summary structure is built from holdings?
                    # If we only show what we hold, checking summary is fine.
                    # If we want to show "Target but 0 holding", we need to ensure summary includes all asset classes.
                    # The current `get_holdings_summary` initializes `categories` from DB.
                    # And `asset_classes` inside categories?
                    # `AssetCategory.objects.select_related('parent').all()` only gets categories.
                    # We need to insure all asset classes are initialized in the summary.
                    pass

        # 3. Calculate Variances (Current - Target)
        for cat_code, cat_data in summary.categories.items():
            for _ac_name, ac_data in cat_data.asset_classes.items():
                for _at_code, at_data in ac_data.account_types.items():
                    at_data.variance = at_data.current - at_data.target
                ac_data.variance_total = ac_data.total - ac_data.target_total

            for at_code in cat_data.account_type_totals:
                cat_data.account_type_variance_totals[at_code] = (
                    cat_data.account_type_totals[at_code]
                    - cat_data.account_type_target_totals[at_code]
                )
            for acc_id in cat_data.account_totals:
                cat_data.account_variance_totals[acc_id] = (
                    cat_data.account_totals[acc_id] - cat_data.account_target_totals[acc_id]
                )
            cat_data.variance_total = cat_data.total - cat_data.target_total

            group_code = category_group_map.get(cat_code, cat_code)
            group_entry = summary.groups[group_code]
            for at_code in group_entry.account_type_totals:
                group_entry.account_type_variance_totals[at_code] = (
                    group_entry.account_type_totals[at_code]
                    - group_entry.account_type_target_totals[at_code]
                )
            for acc_id in group_entry.account_totals:
                group_entry.account_variance_totals[acc_id] = (
                    group_entry.account_totals[acc_id] - group_entry.account_target_totals[acc_id]
                )
            group_entry.variance_total = group_entry.total - group_entry.target_total

        for at_code in summary.account_type_grand_totals:
            summary.account_type_grand_variance_totals[at_code] = (
                summary.account_type_grand_totals[at_code]
                - summary.account_type_grand_target_totals[at_code]
            )
        for acc_id in summary.account_grand_totals:
            summary.account_grand_variance_totals[acc_id] = (
                summary.account_grand_totals[acc_id] - summary.account_grand_target_totals[acc_id]
            )
        summary.grand_variance_total = summary.grand_total - summary.grand_target_total

    @staticmethod
    def _calculate_percentages(summary: PortfolioSummary) -> None:
        """
        Calculate all percentage values for account type aggregations.
        This pre-calculates percentages so templates don't need to do division.
        """

        # Helper function to calculate percentage safely
        def calc_pct(value: Decimal, total: Decimal) -> Decimal:
            if total == 0:
                return Decimal("0")
            return (value / total) * Decimal("100")

        # 1. Calculate percentages for asset class rows (AccountTypeData)
        for cat_data in summary.categories.values():
            for ac_data in cat_data.asset_classes.values():
                for at_code, at_data in ac_data.account_types.items():
                    at_total = summary.account_type_grand_totals.get(at_code, Decimal("0"))
                    at_data.current_pct = calc_pct(at_data.current, at_total)
                    at_data.target_pct = calc_pct(at_data.target, at_total)
                    at_data.variance_pct = at_data.current_pct - at_data.target_pct

        # 2. Calculate percentages for category subtotals
        for cat_data in summary.categories.values():
            for at_code in cat_data.account_type_totals:
                at_total = summary.account_type_grand_totals.get(at_code, Decimal("0"))
                cat_data.account_type_current_pct[at_code] = calc_pct(
                    cat_data.account_type_totals[at_code], at_total
                )
                cat_data.account_type_target_pct[at_code] = calc_pct(
                    cat_data.account_type_target_totals[at_code], at_total
                )
                cat_data.account_type_variance_pct[at_code] = (
                    cat_data.account_type_current_pct[at_code]
                    - cat_data.account_type_target_pct[at_code]
                )

        # 3. Calculate percentages for group totals
        for group_data in summary.groups.values():
            for at_code in group_data.account_type_totals:
                at_total = summary.account_type_grand_totals.get(at_code, Decimal("0"))
                group_data.account_type_current_pct[at_code] = calc_pct(
                    group_data.account_type_totals[at_code], at_total
                )
                group_data.account_type_target_pct[at_code] = calc_pct(
                    group_data.account_type_target_totals[at_code], at_total
                )
                group_data.account_type_variance_pct[at_code] = (
                    group_data.account_type_current_pct[at_code]
                    - group_data.account_type_target_pct[at_code]
                )

        # 4. Calculate percentages for grand totals
        for at_code in summary.account_type_grand_totals:
            at_total = summary.account_type_grand_totals[at_code]
            # For grand totals, current% should always be 100% (current / current)
            summary.account_type_grand_current_pct[at_code] = Decimal("100")
            summary.account_type_grand_target_pct[at_code] = calc_pct(
                summary.account_type_grand_target_totals[at_code], at_total
            )
            summary.account_type_grand_variance_pct[at_code] = (
                summary.account_type_grand_current_pct[at_code]
                - summary.account_type_grand_target_pct[at_code]
            )

    @staticmethod
    def _sort_and_organize_summary(
        summary: PortfolioSummary, category_group_map: dict[str, str]
    ) -> None:
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
            group_entry.asset_class_count += len(category_data.asset_classes)

        sorted_groups = sorted(summary.groups.items(), key=lambda item: item[1].total, reverse=True)
        summary.groups = OrderedDict(sorted_groups)

        grand_total = summary.grand_total
        account_type_percentages: dict[str, Decimal] = {}
        if grand_total > 0:
            for code, value in summary.account_type_grand_totals.items():
                account_type_percentages[code] = (value / grand_total) * Decimal("100")
        else:
            for code in summary.account_type_grand_totals:
                account_type_percentages[code] = Decimal("0.00")

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

        # 1. Fetch Effective Targets
        effective_targets_map = PortfolioSummaryService.get_effective_targets(user)
        # Map: account_id -> asset_class_name -> target_pct

        # Initialize groups dynamically from AccountGroup model
        # We need an OrderedDict to maintain display order
        # Key: group_name, Value: {label, total, accounts}

        # Load all groups ordered by sort_order
        from .models import AccountGroup  # Delayed import to avoid circular dependency if any

        all_groups = AccountGroup.objects.all()
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for g in all_groups:
            groups[g.name] = {"label": g.name, "total": Decimal("0.00"), "accounts": []}

        # Add 'Other' group for unassigned accounts
        if "Other" not in groups:
            groups["Other"] = {"label": "Other", "total": Decimal("0.00"), "accounts": []}

        grand_total = Decimal("0.00")

        for account in accounts:
            account_total = Decimal("0.00")
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

            # account.account_type is the object now, but we use effective targets for this account
            account_targets = effective_targets_map.get(account.id, {})
            all_asset_classes = set(holdings_by_ac.keys()) | set(account_targets.keys())

            absolute_deviation = Decimal("0.00")
            absolute_deviation_pct = Decimal("0.00")

            if account_total > 0:
                for ac_name in all_asset_classes:
                    actual_val = holdings_by_ac.get(ac_name, Decimal("0.00"))
                    target_pct = account_targets.get(ac_name, Decimal("0.00"))
                    target_val = account_total * (target_pct / Decimal("100.00"))
                    absolute_deviation += abs(actual_val - target_val)

                absolute_deviation_pct = (absolute_deviation / account_total) * Decimal("100.00")

            # Determine group
            # Use account.account_type.group
            group_name = "Other"
            if account.account_type.group:
                group_name = account.account_type.group.name

            # If for some reason the group exists on the account but wasn't in our initial fetch (race condition?),
            # fallback to Other or create it dynamically (safer to use Other for now)
            if group_name not in groups:
                group_name = "Other"

            groups[group_name]["accounts"].append(
                {
                    "id": account.id,
                    "name": account.name,
                    "institution": account.institution.name if account.institution else "N/A",
                    "total": account_total,
                    "absolute_deviation": absolute_deviation,
                    "absolute_deviation_pct": absolute_deviation_pct,
                }
            )
            groups[group_name]["total"] += account_total
            grand_total += account_total

        # Filter out "Other" if empty
        if "Other" in groups and not groups["Other"]["accounts"]:
            del groups["Other"]

        # Filter out any other groups that might be empty (e.g., from AccountGroup but no accounts assigned)
        # This ensures we only show groups that actually contain accounts.
        groups_with_accounts = {k: v for k, v in groups.items() if v["accounts"]}

        # Sort accounts within each group
        for group_data in groups_with_accounts.values():
            group_data["accounts"].sort(key=lambda x: x["total"], reverse=True)

        # Sort the groups themselves by their total value
        sorted_groups = dict(
            sorted(groups_with_accounts.items(), key=lambda item: item[1]["total"], reverse=True)
        )

        return {
            "grand_total": grand_total,
            "groups": sorted_groups,
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

        # --- PRE-CALCULATION PHASE ---

        # Use Effective Targets Logic
        # account_id -> asset_class_name -> target_pct
        # Note: get_effective_targets returns map by Asset Class NAME.
        # But get_holdings_by_category iteration uses asset_class_id or object?
        # The holding.security.asset_class has an ID and a Name.
        # Let's map effective targets to (account_id, asset_class_id) if possible?
        # get_effective_targets uses names.
        # We can map names to IDs or use names in the loop.

        effective_targets_map = PortfolioSummaryService.get_effective_targets(user)

        # Calculate Account Totals and Security Counts per Asset Class per Account
        account_totals: dict[int, Decimal] = defaultdict(Decimal)
        # account_id -> asset_class_id -> set of security tickers
        account_ac_security_counts: dict[int, dict[int, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        # Account-level security count mapping since we might filter by account_id but need context
        # Actually, if we filter by account_id, we only care about that account's context.

        # We need to iterate ALL holdings to build the account stats first, even if we are filtering?
        # No, if we filter by account_id, we only show data for that account.

        for holding in holdings_qs:
            val = Decimal("0.00")
            if holding.current_price:
                val = holding.shares * holding.current_price

            account_totals[holding.account_id] += val
            account_ac_security_counts[holding.account_id][holding.security.asset_class_id].add(
                holding.security.ticker
            )

        # --- AGGREGATION PHASE ---

        ticker_data: dict[str, AggregatedHolding] = {}
        grand_total_value = Decimal("0.00")

        for holding in holdings_qs:
            ticker = holding.security.ticker
            current_val = Decimal("0.00")
            if holding.current_price:
                current_val = holding.shares * holding.current_price

            grand_total_value += current_val

            # Determine Target Value for this specific holding instance
            # Target for Asset Class in this Account
            # Use Effective Target
            ac_targets = effective_targets_map.get(holding.account_id, {})
            ac_target_pct = ac_targets.get(holding.security.asset_class.name, Decimal("0.00"))

            # Number of securities in this asset class held in this account
            num_securities = len(
                account_ac_security_counts[holding.account_id][holding.security.asset_class_id]
            )

            # Allocate target evenly among securities
            # If num_securities is 0 (shouldn't happen here), handle division by zero
            security_target_pct = (
                ac_target_pct / Decimal(num_securities) if num_securities > 0 else Decimal("0.00")
            )

            # Dollar Target for this holding
            account_total = account_totals[holding.account_id]
            holding_target_value = account_total * (security_target_pct / Decimal("100.00"))

            # Target Shares
            # If price is 0 or None, we can't calculate target shares reasonably.
            holding_target_shares = Decimal("0.00")
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

            ticker_data[ticker].target_shares += holding_target_shares

        # --- INJECT EMPTY PRE-CALCULATED TARGETS ---
        # Identify asset classes with targets but no holdings for specific accounts

        # 1. Build map of all Asset Classes for lookup
        from .models import AssetClass

        all_asset_classes = AssetClass.objects.values("id", "name", "category_id")
        ac_lookup = {ac["name"]: ac for ac in all_asset_classes}

        # 2. Iterate effective targets and check for missing holdings
        for acc_id, ac_targets in effective_targets_map.items():
            # Skip if we are filtering by account and this isn't it
            if account_id and acc_id != account_id:
                continue

            # Get current account total (needed for target $ calc)
            # If account has 0 value, target $ is 0, so usually doesn't matter to show?
            # But maybe user wants to see what they SHOULD buy?
            # If account total is 0, we can't really recommend buying X dollars unless we know planned deposit.
            # So skipping 0-value accounts is reasonable for now.
            acc_total = account_totals.get(acc_id, Decimal("0.00"))
            if acc_total == 0:
                continue

            for ac_name, target_pct in ac_targets.items():
                if target_pct <= 0:
                    continue

                # Check if we have any holdings for this AC in this account
                # Look at account_ac_security_counts
                ac_id_obj = ac_lookup.get(ac_name)
                if not ac_id_obj:
                    # Target refers to unknown asset class?
                    continue

                ac_id = ac_id_obj["id"]

                has_holdings = False
                if (
                    acc_id in account_ac_security_counts
                    and ac_id in account_ac_security_counts[acc_id]
                ):
                    has_holdings = True

                if not has_holdings:
                    # We have a target but no holdings. Inject placeholder.
                    # We aggregate markers by Asset Class Name (so multiple accounts missing same AC group together)
                    marker_key = f"_EMPTY_{ac_name}"

                    target_val = acc_total * (target_pct / Decimal("100.00"))

                    if marker_key not in ticker_data:
                        ticker_data[marker_key] = AggregatedHolding(
                            ticker="",  # Blank ticker
                            name="",  # Blank name
                            asset_class=ac_name,
                            category_code=ac_id_obj["category_id"],
                            current_price=None,
                            shares=Decimal("0.00"),
                            value=Decimal("0.00"),
                        )

                    ticker_data[marker_key].target_value += target_val
                    # No target shares since no price.

        # --- FINAL METRICS CALCULATION ---

        for holding_data in ticker_data.values():
            # Current Allocation %
            if grand_total_value > 0:
                holding_data.current_allocation = (
                    holding_data.value / grand_total_value
                ) * Decimal("100.00")
                holding_data.target_allocation = (
                    holding_data.target_value / grand_total_value
                ) * Decimal("100.00")

            # Variances
            holding_data.value_variance = holding_data.value - holding_data.target_value
            holding_data.shares_variance = holding_data.shares - holding_data.target_shares
            holding_data.allocation_variance = (
                holding_data.current_allocation - holding_data.target_allocation
            )

        # --- GROUPING ---

        # Now group by category (existing logic)
        categories: defaultdict[str, HoldingsCategory] = defaultdict(
            lambda: HoldingsCategory(label="", holdings=[])
        )
        category_qs = AssetCategory.objects.select_related("parent").order_by("sort_order", "label")
        category_map: dict[str, AssetCategory] = {
            category.code: category for category in category_qs
        }
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
        grand_target_value = Decimal("0.00")
        grand_value_variance = Decimal("0.00")
        grand_current_allocation = Decimal("0.00")
        grand_target_allocation = Decimal("0.00")
        grand_allocation_variance = Decimal("0.00")

        for group_code in group_order:
            category_codes = grouped_category_codes.get(group_code, [])
            group_categories: OrderedDict[str, HoldingsCategory] = OrderedDict()
            group_total = Decimal("0.00")
            group_target_value = Decimal("0.00")
            group_value_variance = Decimal("0.00")
            group_current_allocation = Decimal("0.00")
            group_target_allocation = Decimal("0.00")
            group_allocation_variance = Decimal("0.00")

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
            "holding_groups": holding_groups,
            "grand_total": grand_total_value,
            "grand_target_value": grand_target_value,
            "grand_value_variance": grand_value_variance,
            "grand_current_allocation": grand_current_allocation,
            "grand_target_allocation": grand_target_allocation,
            "grand_allocation_variance": grand_allocation_variance,
        }

from __future__ import annotations

import logging
from collections import OrderedDict, defaultdict
from decimal import Decimal
from typing import Any

from portfolio.models import Account, AssetClassCategory, Holding
from portfolio.services.pricing import PricingService
from portfolio.services.targets import TargetAllocationService
from portfolio.structs import AggregatedHolding, HoldingsCategory, HoldingsGroup, PortfolioSummary
from users.models import CustomUser

logger = logging.getLogger(__name__)


class PortfolioSummaryService:
    """Orchestrates portfolio data retrieval and builds view models.

    Delegates to:
    - PricingService for price updates
    - TargetAllocationService for target resolution
    - (Later) Portfolio aggregate for higher-level calculations
    """

    def __init__(
        self,
        pricing_service: PricingService | None = None,
        target_service: TargetAllocationService | None = None,
    ) -> None:
        self._pricing = pricing_service or PricingService()
        self._targets = target_service or TargetAllocationService()

    def update_prices(self, user: CustomUser) -> None:
        """Fetch current prices and update Holding.current_price for all user holdings."""

        self._pricing.update_holdings_prices(user)

    def get_effective_targets(self, user: CustomUser) -> dict[int, dict[str, Decimal]]:
        """Get effective target allocation percentages per account/asset class."""

        return TargetAllocationService.get_effective_targets(user)

    def get_holdings_summary(self, user: CustomUser) -> PortfolioSummary:
        """Aggregate holdings and targets into a PortfolioSummary struct.

        Currently reuses the existing aggregation logic while routing all
        service calls through injected collaborators. A later refactor step
        can replace the internals with logic based on the Portfolio aggregate.
        """

        # Ensure prices are up to date. Use the static wrapper so tests that
        # patch PortfolioSummaryService.update_prices continue to work.
        self.update_prices(user)

        holdings = Holding.objects.get_for_summary(user)
        categories = AssetClassCategory.objects.select_related("parent").all()
        return self._build_summary(user, holdings, categories)

    def _build_summary(self, user: CustomUser, holdings: Any, categories: Any) -> PortfolioSummary:
        """Build a PortfolioSummary from holdings and category data.

        This helper encapsulates the construction of the PortfolioSummary
        struct from the raw querysets. A later refactor can change the
        parameters to operate on a Portfolio aggregate instead, while keeping
        callers stable.
        """

        category_labels, category_group_map, group_labels = self._build_category_maps(categories)

        summary = PortfolioSummary(
            category_labels=category_labels,
            group_labels=group_labels,
        )

        # Pre-initialize asset classes in summary so targets can be filled even if no holdings.
        from portfolio.models import AssetClass

        all_asset_classes = AssetClass.objects.select_related("category").all()
        for ac in all_asset_classes:
            cat_code = ac.category.code
            if cat_code not in summary.categories:
                # The PortfolioSummary dataclass uses default dicts, so simply
                # accessing the category will initialize it.
                _ = summary.categories[cat_code]
            ac_entry = summary.categories[cat_code].asset_classes[ac.name]
            ac_entry.id = ac.id

        account_totals: dict[int, Decimal] = defaultdict(Decimal)
        account_type_map: dict[int, str] = {}

        self._aggregate_holdings(
            summary, holdings, category_group_map, group_labels, account_totals, account_type_map
        )

        self._calculate_targets_and_variances(
            user, summary, category_group_map, account_totals, account_type_map
        )

        self._calculate_percentages(summary)
        self._sort_and_organize_summary(summary, category_group_map)

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
            if not holding.has_price:
                continue

            value = holding.market_value

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

            ac_entry = summary.categories[category_code].asset_classes[asset_class_name]
            if ac_entry.id is None:
                ac_entry.id = asset_class.id
            ac_entry.account_types[account_type_code].current += value
            ac_entry.total += value

            cat_entry = summary.categories[category_code]
            cat_entry.total += value
            cat_entry.account_type_totals[account_type_code] += value
            cat_entry.account_totals[holding.account_id] += value

            group_code = category_group_map.get(category_code, category_code)
            group_entry = summary.groups[group_code]
            if not group_entry.label:
                group_entry.label = group_labels.get(group_code, group_code)

            group_entry.total += value
            group_entry.account_type_totals[account_type_code] += value
            group_entry.account_totals[holding.account_id] += value

            summary.grand_total += value
            summary.account_type_grand_totals[account_type_code] += value
            summary.account_grand_totals[holding.account_id] += value

    def _calculate_targets_and_variances(
        self,
        user: CustomUser,
        summary: PortfolioSummary,
        category_group_map: dict[str, str],
        account_totals: dict[int, Decimal],
        account_type_map: dict[int, str],  # account_id -> account_type_code
    ) -> None:
        effective_targets = self.get_effective_targets(user)

        for account_id, ac_targets in effective_targets.items():
            account_total = account_totals.get(account_id, Decimal("0.00"))
            if account_total == 0:
                continue

            at_code = account_type_map.get(account_id)
            if not at_code:
                continue

            for asset_class_name, target_pct in ac_targets.items():
                target_dollars = account_total * (target_pct / Decimal("100.00"))

                found = False
                for cat_code, cat_data in summary.categories.items():
                    if asset_class_name in cat_data.asset_classes:
                        ac_data = cat_data.asset_classes[asset_class_name]
                        ac_data.account_types[at_code].target += target_dollars
                        ac_data.target_total += target_dollars

                        if ac_data.id is not None:
                            summary.account_asset_targets[account_id][ac_data.id] += target_dollars

                        cat_data.account_type_target_totals[at_code] += target_dollars
                        cat_data.account_target_totals[account_id] += target_dollars
                        cat_data.target_total += target_dollars

                        group_code = category_group_map.get(cat_code, cat_code)
                        group_entry = summary.groups[group_code]
                        group_entry.account_type_target_totals[at_code] += target_dollars
                        group_entry.account_target_totals[account_id] += target_dollars
                        group_entry.target_total += target_dollars

                        summary.account_type_grand_target_totals[at_code] += target_dollars
                        summary.account_grand_target_totals[account_id] += target_dollars
                        summary.grand_target_total += target_dollars

                        found = True
                        break

                if not found:
                    # Asset class might exist in targets but not in current summary (no holdings).
                    # The existing implementation effectively ignores these.
                    pass

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
        """Calculate percentage values for all aggregations to avoid template math."""

        def calc_pct(value: Decimal, total: Decimal) -> Decimal:
            if total == 0:
                return Decimal("0")
            return (value / total) * Decimal("100")

        for cat_data in summary.categories.values():
            for ac_data in cat_data.asset_classes.values():
                for at_code, at_data in ac_data.account_types.items():
                    at_total = summary.account_type_grand_totals.get(at_code, Decimal("0"))
                    at_data.current_pct = calc_pct(at_data.current, at_total)
                    at_data.target_pct = calc_pct(at_data.target, at_total)
                    at_data.variance_pct = at_data.current_pct - at_data.target_pct

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

        for at_code in summary.account_type_grand_totals:
            at_total = summary.account_type_grand_totals[at_code]
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

    def get_account_summary(self, user: CustomUser) -> dict[str, Any]:
        """Get summary of accounts grouped by AccountGroup.

        Includes aggregate absolute deviation from target allocation for each account.
        """

        # Ensure prices are up to date
        self.update_prices(user)

        # Prefetch data using Manager
        accounts = Account.objects.get_summary_data(user)

        # 1. Fetch Effective Targets
        effective_targets_map = self.get_effective_targets(user)
        # Map: account_id -> asset_class_name -> target_pct

        from portfolio.models import AccountGroup

        all_groups = AccountGroup.objects.all()
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for g in all_groups:
            groups[g.name] = {"label": g.name, "total": Decimal("0.00"), "accounts": []}

        if "Other" not in groups:
            groups["Other"] = {"label": "Other", "total": Decimal("0.00"), "accounts": []}

        grand_total = Decimal("0.00")

        for account in accounts:
            account_total = account.total_value()

            account_targets = effective_targets_map.get(account.id, {})

            absolute_deviation = account.calculate_deviation(account_targets)
            absolute_deviation_pct = Decimal("0.00")
            if account_total > 0:
                absolute_deviation_pct = (absolute_deviation / account_total) * Decimal("100.00")

            group_name = "Other"
            if account.account_type.group:
                group_name = account.account_type.group.name

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

        if "Other" in groups and not groups["Other"]["accounts"]:
            del groups["Other"]

        groups_with_accounts = {k: v for k, v in groups.items() if v["accounts"]}

        for group_data in groups_with_accounts.values():
            group_data["accounts"].sort(key=lambda x: x["total"], reverse=True)

        sorted_groups = dict(
            sorted(groups_with_accounts.items(), key=lambda item: item[1]["total"], reverse=True)
        )

        return {
            "grand_total": grand_total,
            "groups": sorted_groups,
        }

    def get_holdings_by_category(self, user: CustomUser, account_id: int | None = None) -> dict[str, Any]:
        """Get holdings grouped by category/group, including target and variance data."""

        self.update_prices(user)

        holdings_qs = Holding.objects.get_for_category_view(user)
        if account_id:
            holdings_qs = holdings_qs.filter(account_id=account_id)

        effective_targets_map = self.get_effective_targets(user)

        account_totals: dict[int, Decimal] = defaultdict(Decimal)
        account_ac_security_counts: dict[int, dict[int, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )

        for holding in holdings_qs:
            val = Decimal("0.00")
            if holding.current_price:
                val = holding.shares * holding.current_price

            account_totals[holding.account_id] += val
            account_ac_security_counts[holding.account_id][holding.security.asset_class_id].add(
                holding.security.ticker
            )

        ticker_data: dict[str, AggregatedHolding] = {}
        grand_total_value = Decimal("0.00")

        for holding in holdings_qs:
            ticker = holding.security.ticker
            current_val = Decimal("0.00")
            if holding.current_price:
                current_val = holding.shares * holding.current_price

            grand_total_value += current_val

            ac_targets = effective_targets_map.get(holding.account_id, {})
            ac_target_pct = ac_targets.get(holding.security.asset_class.name, Decimal("0.00"))

            num_securities = len(
                account_ac_security_counts[holding.account_id][holding.security.asset_class_id]
            )

            security_target_pct = (
                ac_target_pct / Decimal(num_securities) if num_securities > 0 else Decimal("0.00")
            )

            account_total = account_totals[holding.account_id]
            holding_target_value = account_total * (security_target_pct / Decimal("100.00"))

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

        from portfolio.models import AssetClass

        all_asset_classes = AssetClass.objects.values("id", "name", "category_id")
        ac_lookup = {ac["name"]: ac for ac in all_asset_classes}

        for acc_id, ac_targets in effective_targets_map.items():
            if account_id and acc_id != account_id:
                continue

            acc_total = account_totals.get(acc_id, Decimal("0.00"))
            if acc_total == 0:
                continue

            for ac_name, target_pct in ac_targets.items():
                if target_pct <= 0:
                    continue

                ac_id_obj = ac_lookup.get(ac_name)
                if not ac_id_obj:
                    continue

                ac_id = ac_id_obj["id"]

                has_holdings = False
                if (
                    acc_id in account_ac_security_counts
                    and ac_id in account_ac_security_counts[acc_id]
                ):
                    has_holdings = True

                if not has_holdings:
                    # Targets with no current holdings are ignored in the current implementation.
                    continue

        # Build HoldingsCategory/Group structure from ticker_data, grouping by
        # parent category code (e.g. EQUITIES) while keeping child categories
        # (e.g. US_EQUITIES) inside each group. This matches the original
        # behavior expected by existing tests.

        # Build category -> group mappings and labels
        categories = AssetClassCategory.objects.select_related("parent").all()
        category_group_map: dict[str, str] = {}
        group_labels: dict[str, str] = {}
        category_labels: dict[str, str] = {}

        for category in categories:
            parent_category = category.parent or category
            category_group_map[category.code] = parent_category.code
            group_labels.setdefault(parent_category.code, parent_category.label)
            category_labels[category.code] = category.label

        holding_groups: dict[str, HoldingsGroup] = {}

        for agg in ticker_data.values():
            group_code = category_group_map.get(agg.category_code, agg.category_code)

            if group_code not in holding_groups:
                holding_groups[group_code] = HoldingsGroup(
                    label=group_labels.get(group_code, group_code),
                    total=Decimal("0.00"),
                )

            holdings_group = holding_groups[group_code]
            holdings_group.total += agg.value

            if agg.category_code not in holdings_group.categories:
                holdings_group.categories[agg.category_code] = HoldingsCategory(
                    label=category_labels.get(agg.category_code, agg.category_code),
                    total=Decimal("0.00"),
                    holdings=[],
                )

            holding_category = holdings_group.categories[agg.category_code]
            holding_category.total += agg.value
            holding_category.holdings.append(agg)

        return {
            "grand_total": grand_total_value,
            "holding_groups": holding_groups,
        }

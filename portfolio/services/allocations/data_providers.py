"""Data access layer for allocation calculations."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import F

import pandas as pd
import structlog

if TYPE_CHECKING:
    from portfolio.models import AssetClass, Holding, Security

logger = structlog.get_logger(__name__)


class DjangoDataProvider:
    """Optimized Django ORM data provider using pandas DataFrames."""

    def get_holdings_df(self, user: Any) -> pd.DataFrame:
        """
        Get all holdings as long-format DataFrame.

        Returns DataFrame with columns:
            account_id, account_name, account_type_code, asset_class,
            asset_class_id, category_code, ticker, shares, price, value
        """
        from django.db.models import OuterRef, Subquery

        from portfolio.models import Holding, SecurityPrice

        # Subquery for latest price to avoid N+1 and duplicates
        latest_price = Subquery(
            SecurityPrice.objects.filter(security_id=OuterRef("security_id"))
            .order_by("-price_datetime")
            .values("price")[:1]
        )

        # Django 6.0: Optimized query with annotations
        qs = (
            Holding.objects.filter(account__portfolio__user=user)
            .select_related(
                "account__account_type",
                "security__asset_class__category__parent",
            )
            .annotate(
                price=latest_price,
                value=F("shares") * F("price"),
            )
            .values(
                "account_id",
                "account__name",
                "account__account_type__code",
                "security__asset_class__name",
                "security__asset_class__id",
                "security__asset_class__category__code",
                "security__ticker",
                "shares",
                "price",
                "value",
            )
        )

        if not qs.exists():
            return pd.DataFrame()

        # Pandas 2.3: Direct DataFrame construction
        df = pd.DataFrame.from_records(qs, coerce_float=True)

        # Standardize column names
        df.columns = [
            "account_id",
            "account_name",
            "account_type_code",
            "asset_class",
            "asset_class_id",
            "category_code",
            "ticker",
            "shares",
            "price",
            "value",
        ]

        return df

    def get_asset_classes_df(self, user: Any) -> pd.DataFrame:
        """Get asset class metadata as DataFrame."""
        from portfolio.models import AssetClass

        qs = AssetClass.objects.select_related("category", "category__parent").values(
            "id",
            "name",
            "category__parent__code",
            "category__parent__label",
            "category__parent__sort_order",
            "category__code",
            "category__label",
            "category__sort_order",
        )

        df = pd.DataFrame(list(qs))
        if df.empty:
            return df

        df.columns = [
            "asset_class_id",
            "asset_class_name",
            "group_code",
            "group_label",
            "group_sort_order",
            "category_code",
            "category_label",
            "category_sort_order",
        ]

        # Pandas 2.3: nullable boolean dtype
        df["is_cash"] = (
            (df["category_code"] == "CASH") | (df["asset_class_name"] == "Cash")
        ).astype("boolean")

        # Set row_type for individual asset class rows
        df["row_type"] = "asset_class"

        return df

    def get_accounts_metadata(self, user: Any) -> tuple[list[dict], dict[int, list[dict]]]:
        """
        Get account metadata grouped by type.

        Returns:
            (list of all accounts, dict of {type_id: [accounts]})
        """
        from collections import defaultdict

        from portfolio.models import Account

        accounts = list(
            Account.objects.filter(user=user)
            .select_related("account_type", "account_type__group", "institution")
            .values(
                "id",
                "name",
                "account_type__id",
                "account_type__code",
                "account_type__label",
                "account_type__group__name",
                "institution__name",
            )
        )

        # Group by type
        by_type = defaultdict(list)
        for acc in accounts:
            type_id = acc["account_type__id"]
            by_type[type_id].append(
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "type_code": acc["account_type__code"],
                    "type_label": acc["account_type__label"],
                    "institution": acc["institution__name"],
                }
            )

        return accounts, dict(by_type)

    def get_targets_map(self, user: Any) -> dict[int, dict[str, Decimal]]:
        """
        Get effective target allocations for all accounts.

        Returns dict: {account_id: {asset_class_name: target_pct}}
        """
        from portfolio.models import Account

        accounts = Account.objects.filter(user=user).select_related(
            "allocation_strategy",
            "account_type",
            "portfolio__allocation_strategy",
        )

        result = {}
        for account in accounts:
            # Use the Account model's existing method
            allocations = account.get_target_allocations_by_name()
            if allocations:
                result[account.id] = allocations

        return result

    def get_target_strategies(self, user: Any) -> dict[str, dict[int, int]]:
        """
        Get strategy assignments for account types and accounts.

        Returns:
            Dict containing:
            - at_strategy_map: {account_type_id: strategy_id}
            - acc_strategy_map: {account_id: strategy_id}
        """
        from portfolio.models import Account, AccountTypeStrategyAssignment

        # 1. Account Type Assignments
        at_assignments = AccountTypeStrategyAssignment.objects.filter(user=user).values(
            "account_type_id", "allocation_strategy_id"
        )

        at_map = {
            item["account_type_id"]: item["allocation_strategy_id"] for item in at_assignments
        }

        # 2. Individual Account Overrides
        acc_assignments = (
            Account.objects.filter(user=user)
            .exclude(allocation_strategy__isnull=True)
            .values("id", "allocation_strategy_id")
        )

        acc_map = {item["id"]: item["allocation_strategy_id"] for item in acc_assignments}

        return {
            "at_strategy_map": at_map,
            "acc_strategy_map": acc_map,
        }

    def get_policy_targets(self, user: Any) -> dict[str, Decimal]:
        """
        Get portfolio-level policy targets from the portfolio's allocation strategy.

        Policy targets represent the user's stated target allocation for their
        entire portfolio, as opposed to effective targets which are weighted
        averages of account-level targets.

        Returns:
            Dict of {asset_class_name: target_percent}
            Empty dict if no portfolio strategy is assigned.
        """
        from portfolio.models import Portfolio

        # Get user's portfolio with its allocation strategy
        portfolio = (
            Portfolio.objects.filter(user=user).select_related("allocation_strategy").first()
        )

        if not portfolio or not portfolio.allocation_strategy:
            return {}

        return portfolio.allocation_strategy.get_allocations_by_name()

    def get_holdings_df_detailed(self, user: Any, account_id: int | None = None) -> pd.DataFrame:
        """
        Get detailed holdings DataFrame with all metadata for holdings view.

        Returns DataFrame with columns:
            Account_ID, Account_Name, Account_Type, Ticker, Security_Name,
            Asset_Class, Asset_Class_ID, Asset_Category, Asset_Group,
            Group_Code, Group_Sort_Order, Category_Code, Category_Sort_Order,
            Shares, Price, Value

        Args:
            user: User object
            account_id: Optional account ID to filter to single account
        """
        from django.db.models import OuterRef, Subquery

        from portfolio.models import Holding, SecurityPrice

        # Subquery for latest price
        latest_price = Subquery(
            SecurityPrice.objects.filter(security_id=OuterRef("security_id"))
            .order_by("-price_datetime")
            .values("price")[:1]
        )

        # Build queryset
        qs = Holding.objects.filter(account__portfolio__user=user).select_related(
            "account__account_type",
            "security__asset_class__category__parent",
        )

        if account_id:
            qs = qs.filter(account_id=account_id)

        qs = qs.annotate(
            price=latest_price,
            value=F("shares") * F("price"),
        ).values(
            "account_id",
            "account__name",
            "account__account_type__label",
            "security__ticker",
            "security__name",
            "security__asset_class__name",
            "security__asset_class__id",
            "security__asset_class__category__label",
            "security__asset_class__category__parent__label",
            "security__asset_class__category__parent__code",
            "security__asset_class__category__parent__sort_order",
            "security__asset_class__category__code",
            "security__asset_class__category__sort_order",
            "shares",
            "price",
            "value",
        )

        if not qs.exists():
            return pd.DataFrame()

        df = pd.DataFrame.from_records(qs, coerce_float=True)

        # Rename columns to expected format
        df.columns = [
            "Account_ID",
            "Account_Name",
            "Account_Type",
            "Ticker",
            "Security_Name",
            "Asset_Class",
            "Asset_Class_ID",
            "Asset_Category",
            "Asset_Group",
            "Group_Code",
            "Group_Sort_Order",
            "Category_Code",
            "Category_Sort_Order",
            "Shares",
            "Price",
            "Value",
        ]

        # Fill missing group data (for asset classes without parent category)
        df["Asset_Group"] = df["Asset_Group"].fillna(df["Asset_Category"])
        df["Group_Code"] = df["Group_Code"].fillna(df["Category_Code"])
        df["Group_Sort_Order"] = df["Group_Sort_Order"].fillna(df["Category_Sort_Order"])

        return df

    def _create_zero_holding_dict(
        self,
        asset_class: AssetClass,
        security: Security,
        account_id: int = 0,
    ) -> dict[str, Any]:
        """
        Create a zero-holding dictionary for an asset class.

        Args:
            asset_class: AssetClass with primary security
            security: Security to use for the holding
            account_id: Account ID (0 for portfolio-level)

        Returns:
            Dict with standard holdings schema, Value=0
        """
        from portfolio.models import SecurityPrice

        category = asset_class.category

        # Get latest price for the security
        latest_price = SecurityPrice.get_latest_price(security)
        price = float(latest_price) if latest_price else 0.0

        return {
            "Account_ID": account_id,
            "Account_Name": "Portfolio" if account_id == 0 else "",
            "Account_Type": "",
            "Ticker": security.ticker,
            "Security_Name": security.name,
            "Asset_Class": asset_class.name,
            "Asset_Class_ID": asset_class.id,
            "Asset_Category": category.label,
            "Asset_Group": (category.parent.label if category.parent else category.label),
            "Group_Code": (category.parent.code if category.parent else category.code),
            "Group_Sort_Order": (
                category.parent.sort_order if category.parent else category.sort_order
            ),
            "Category_Code": category.code,
            "Category_Sort_Order": category.sort_order,
            "Shares": 0.0,
            "Price": price,
            "Value": 0.0,
        }

    def get_zero_holdings_for_targets(
        self,
        existing_df: pd.DataFrame,
        targets_map: dict[int, dict[str, Decimal]],
        account_id: int = 0,
    ) -> pd.DataFrame:
        """
        Create zero-holding rows for asset classes with targets but no holdings.

        Args:
            existing_df: Existing holdings DataFrame
            targets_map: {account_id: {asset_class_name: target_pct}}
            account_id: Account ID (0 for portfolio-wide aggregation)

        Returns:
            DataFrame with zero-holding rows for missing asset classes
        """
        from portfolio.models import AssetClass

        account_targets = targets_map.get(account_id, {})
        if not account_targets:
            return pd.DataFrame()

        # Find missing asset classes
        existing_asset_classes = set()
        if not existing_df.empty and "Asset_Class" in existing_df.columns:
            existing_asset_classes = set(existing_df["Asset_Class"].unique())

        missing_asset_classes = set(account_targets.keys()) - existing_asset_classes

        if not missing_asset_classes:
            return pd.DataFrame()

        # Build zero holdings using helper method
        zero_holdings = []

        for ac_name in missing_asset_classes:
            try:
                asset_class = AssetClass.objects.select_related(
                    "primary_security", "category", "category__parent"
                ).get(name=ac_name)

                security = asset_class.primary_security
                if not security:
                    logger.warning(
                        "no_primary_security_for_asset_class",
                        asset_class=ac_name,
                        account_id=account_id,
                    )
                    continue

                # Use helper to create zero holding dict
                zero_holding = self._create_zero_holding_dict(
                    asset_class=asset_class,
                    security=security,
                    account_id=account_id,
                )
                zero_holdings.append(zero_holding)

            except AssetClass.DoesNotExist:
                logger.warning("asset_class_not_found", name=ac_name)
                continue

        if not zero_holdings:
            return pd.DataFrame()

        logger.info(
            "created_zero_holdings",
            count=len(zero_holdings),
            asset_classes=[h["Asset_Class"] for h in zero_holdings],
            account_id=account_id,
        )

        return pd.DataFrame(zero_holdings)

    def get_effective_targets_for_portfolio(self, user: Any) -> dict[int, dict[str, Decimal]]:
        """
        Get weighted-average effective targets for portfolio as a whole.

        Returns targets in format: {0: {asset_class_name: target_pct}}
        where 0 is the synthetic portfolio account ID.
        """
        from portfolio.models import Account

        # Get all accounts with their targets and totals
        accounts = Account.objects.filter(user=user).select_related(
            "allocation_strategy",
            "account_type",
            "portfolio__allocation_strategy",
        )

        # Calculate account totals and targets
        account_totals = {}
        account_targets = {}

        for account in accounts:
            total = account.total_value()
            account_totals[account.id] = total

            allocations = account.get_target_allocations_by_name()
            if allocations:
                account_targets[account.id] = allocations

        portfolio_total = sum(account_totals.values(), Decimal("0.00"))

        if portfolio_total == 0:
            return {0: {}}

        # Calculate weighted average
        portfolio_targets: dict[str, Decimal] = {}

        for account_id, targets in account_targets.items():
            account_value = account_totals.get(account_id, Decimal("0.00"))
            weight = float(account_value / portfolio_total)

            for asset_class, target_pct in targets.items():
                if asset_class not in portfolio_targets:
                    portfolio_targets[asset_class] = Decimal("0.00")
                portfolio_targets[asset_class] += Decimal(str(float(target_pct) * weight))

        return {0: portfolio_targets}

    def get_policy_targets_for_portfolio(self, user: Any) -> dict[int, dict[str, Decimal]]:
        """
        Get portfolio-level policy targets in holdings format.

        Returns targets in format: {0: {asset_class_name: target_pct}}
        where 0 is the synthetic portfolio account ID.
        """
        policy_targets = self.get_policy_targets(user)
        return {0: policy_targets} if policy_targets else {0: {}}

    # ========================================================================
    # Shared DataFrame Building Helpers
    # ========================================================================

    def holdings_to_dataframe(
        self,
        holdings: list[Holding],
        prices: dict[Security, Decimal] | None = None,
        account_id: int | None = None,
    ) -> pd.DataFrame:
        """
        Convert Django Holding objects to DataFrame format.

        Shared helper used by both allocation views and rebalancing engine.
        Produces a DataFrame with the same schema as get_holdings_df_detailed().

        Args:
            holdings: List of Holding model objects
            prices: Optional dict mapping Security to price. If not provided,
                    uses the latest price from security.prices
            account_id: Optional account ID override (for rebalancing where
                       all holdings are from the same account)

        Returns:
            DataFrame with columns: Account_ID, Account_Name, Account_Type,
            Ticker, Security_Name, Asset_Class, Asset_Class_ID, Asset_Category,
            Asset_Group, Group_Code, Group_Sort_Order, Category_Code,
            Category_Sort_Order, Shares, Price, Value
        """
        if not holdings:
            return pd.DataFrame()

        holdings_data = []
        for h in holdings:
            # Get price from provided dict or from security's latest price
            if prices is not None:
                price = prices.get(h.security, Decimal("0"))
            else:
                price = h.security.latest_price or Decimal("0")

            value = h.shares * price
            asset_class = h.security.asset_class
            category = asset_class.category

            holdings_data.append(
                {
                    "Account_ID": account_id if account_id is not None else h.account_id,
                    "Account_Name": h.account.name if hasattr(h, "account") else "",
                    "Account_Type": (
                        h.account.account_type.label
                        if hasattr(h, "account") and h.account.account_type
                        else ""
                    ),
                    "Ticker": h.security.ticker,
                    "Security_Name": h.security.name,
                    "Asset_Class": asset_class.name,
                    "Asset_Class_ID": asset_class.id,
                    "Asset_Category": category.label,
                    "Asset_Group": (category.parent.label if category.parent else category.label),
                    "Group_Code": (category.parent.code if category.parent else category.code),
                    "Group_Sort_Order": (
                        category.parent.sort_order if category.parent else category.sort_order
                    ),
                    "Category_Code": category.code,
                    "Category_Sort_Order": category.sort_order,
                    "Shares": float(h.shares),
                    "Price": float(price),
                    "Value": float(value),
                }
            )

        return pd.DataFrame(holdings_data)

    def securities_to_dataframe(
        self,
        positions: dict[Security, Decimal],
        prices: dict[Security, Decimal],
        account_id: int,
    ) -> pd.DataFrame:
        """
        Convert a positions dict (security -> shares) to DataFrame format.

        Used for pro forma calculations where we don't have Holding objects
        but rather a dict of security to share counts.

        Args:
            positions: Dict mapping Security to share count (positive only)
            prices: Dict mapping Security to current price
            account_id: Account ID to use for all rows

        Returns:
            DataFrame with same schema as holdings_to_dataframe()
        """
        if not positions:
            return pd.DataFrame()

        holdings_data = []
        for security, shares in positions.items():
            if shares <= 0:
                continue

            price = prices.get(security, Decimal("0"))
            value = shares * price
            asset_class = security.asset_class
            category = asset_class.category

            holdings_data.append(
                {
                    "Account_ID": account_id,
                    "Account_Name": "",
                    "Account_Type": "",
                    "Ticker": security.ticker,
                    "Security_Name": security.name,
                    "Asset_Class": asset_class.name,
                    "Asset_Class_ID": asset_class.id,
                    "Asset_Category": category.label,
                    "Asset_Group": (category.parent.label if category.parent else category.label),
                    "Group_Code": (category.parent.code if category.parent else category.code),
                    "Group_Sort_Order": (
                        category.parent.sort_order if category.parent else category.sort_order
                    ),
                    "Category_Code": category.code,
                    "Category_Sort_Order": category.sort_order,
                    "Shares": float(shares),
                    "Price": float(price),
                    "Value": float(value),
                }
            )

        return pd.DataFrame(holdings_data)

    def get_security_prices(
        self,
        securities: set[Security],
        include_primary_for_asset_classes: set[AssetClass] | None = None,
    ) -> dict[Security, Decimal]:
        """
        Fetch latest prices for securities.

        Optionally includes primary securities for asset classes even if not
        currently held (useful for rebalancing where we may buy into new classes).

        Args:
            securities: Set of Security objects to get prices for
            include_primary_for_asset_classes: Optional set of AssetClass objects
                for which to include the primary security even if not in securities

        Returns:
            Dict mapping Security to latest price (Decimal("0") if no price found)
        """
        from portfolio.models import Security as SecurityModel
        from portfolio.models import SecurityPrice

        all_securities = set(securities)

        # Add primary securities for asset classes if requested
        if include_primary_for_asset_classes:
            existing_ac_ids = {s.asset_class_id for s in securities}

            for asset_class in include_primary_for_asset_classes:
                if asset_class.id not in existing_ac_ids:
                    primary = self._get_primary_security_for_asset_class(asset_class)
                    if primary:
                        all_securities.add(primary)

        if not all_securities:
            return {}

        # Fetch prices - use subquery approach that works on all databases
        from django.db.models import OuterRef, Subquery

        security_ids = [s.id for s in all_securities]

        # Subquery to get latest price for each security
        latest_price_subquery = Subquery(
            SecurityPrice.objects.filter(security_id=OuterRef("pk"))
            .order_by("-price_datetime")
            .values("price")[:1]
        )

        # Fetch securities with their latest prices annotated

        securities_with_prices = SecurityModel.objects.filter(id__in=security_ids).annotate(
            latest_price_value=latest_price_subquery
        )

        # Build price map
        price_map = {s.id: s.latest_price_value for s in securities_with_prices}

        # Build result dict
        prices: dict[Security, Decimal] = {}
        for security in all_securities:
            price = price_map.get(security.id)
            prices[security] = price if price is not None else Decimal("0")

        return prices

    def _get_primary_security_for_asset_class(
        self,
        asset_class: AssetClass,
    ) -> Security | None:
        """
        Get primary security for an asset class with fallback.

        Uses the is_primary flag if available, otherwise returns the first security
        in the asset class ordered by ticker (matching original engine.py behavior).

        Args:
            asset_class: AssetClass to get primary security for

        Returns:
            Security object or None if no securities exist for this class
        """
        from portfolio.models import Security as SecurityModel

        # Try is_primary flag first
        primary = SecurityModel.objects.filter(
            asset_class=asset_class,
            is_primary=True,
        ).first()

        if primary:
            return primary

        # Fallback to first security by ticker
        return SecurityModel.objects.filter(asset_class=asset_class).order_by("ticker").first()

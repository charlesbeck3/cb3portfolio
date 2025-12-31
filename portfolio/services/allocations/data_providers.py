"""Data access layer for allocation calculations."""

from decimal import Decimal
from typing import Any

from django.db.models import F

import pandas as pd
import structlog

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

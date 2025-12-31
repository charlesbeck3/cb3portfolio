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
            .select_related("account_type", "institution")
            .values(
                "id",
                "name",
                "account_type__id",
                "account_type__code",
                "account_type__label",
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

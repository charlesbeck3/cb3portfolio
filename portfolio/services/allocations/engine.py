"""Main allocation calculation engine using composition."""

from collections import OrderedDict
from decimal import Decimal
from typing import Any

import structlog

from .calculations import AllocationCalculator
from .data_providers import DjangoDataProvider
from .formatters import AllocationFormatter
from .types import SidebarData

logger = structlog.get_logger(__name__)


class AllocationEngine:
    """
    Main engine for allocation calculations.

    Uses composition pattern with injected dependencies.
    """

    def __init__(
        self,
        calculator: AllocationCalculator | None = None,
        data_provider: DjangoDataProvider | None = None,
        formatter: AllocationFormatter | None = None,
    ):
        self.calculator = calculator or AllocationCalculator()
        self.data_provider = data_provider or DjangoDataProvider()
        self.formatter = formatter or AllocationFormatter()

    def get_presentation_rows(self, user: Any) -> list[dict[str, Any]]:
        """
        Calculate and format allocation data for dashboard/targets views.

        Replaces old AllocationCalculationEngine.get_presentation_rows()
        with clean, testable architecture.
        """
        logger.info("building_presentation_rows", user_id=user.id)

        try:
            # Step 1: Get all required data
            holdings_df = self.data_provider.get_holdings_df(user)
            if holdings_df.empty:
                logger.info("no_holdings_for_presentation", user_id=user.id)
                return []

            asset_classes_df = self.data_provider.get_asset_classes_df(user)
            targets_map = self.data_provider.get_targets_map(user)
            accounts_list, accounts_by_type = self.data_provider.get_accounts_metadata(user)

            # Step 2: Calculate account totals
            account_totals = (
                holdings_df.groupby("account_id")["value"]
                .sum()
                .apply(lambda x: Decimal(str(x)))
                .to_dict()
            )

            # Step 3: Run calculation pipeline
            presentation_df = self.calculator.build_presentation_dataframe(
                holdings_df=holdings_df,
                asset_classes_df=asset_classes_df,
                targets_map=targets_map,
                account_totals=account_totals,
            )

            if presentation_df.empty:
                return []

            # Step 4: Format for templates
            rows = self.formatter.to_presentation_rows(
                df=presentation_df,
                accounts_by_type=accounts_by_type,
            )

            logger.info(
                "presentation_rows_built",
                user_id=user.id,
                row_count=len(rows),
            )

            return rows

        except Exception as e:
            logger.error(
                "presentation_rows_build_failed",
                user_id=user.id,
                error=str(e),
                exc_info=True,
            )
            return []

    def get_holdings_rows(self, user: Any, account_id: int | None = None) -> list[dict]:
        """
        Calculate and format holdings data for holdings view.

        Note: This is a placeholder - full implementation will be added
        in Phase 6 (formatters).
        """
        logger.info("building_holdings_rows", user_id=user.id, account_id=account_id)

        holdings_df = self.data_provider.get_holdings_df(user)
        if account_id:
            holdings_df = holdings_df[holdings_df["account_id"] == account_id]

        if holdings_df.empty:
            return []

        # TODO: Implement full holdings logic in Phase 6
        logger.warning("get_holdings_rows_not_fully_implemented")
        return []

    def get_sidebar_data(self, user: Any) -> SidebarData:
        """
        Get sidebar data using vectorized operations.

        Replaces nested loop implementation with pandas.
        """
        from django.conf import settings
        from django.db import connection

        logger.info("building_sidebar_data", user_id=user.id)

        initial_queries = len(connection.queries) if settings.DEBUG else 0

        try:
            # Get data
            holdings_df = self.data_provider.get_holdings_df(user)
            accounts_list, _ = self.data_provider.get_accounts_metadata(user)
            targets_map = self.data_provider.get_targets_map(user)

            # Calculate metrics (vectorized)
            metrics = self.calculator.calculate_sidebar_metrics(holdings_df, targets_map)

            # Build groups structure
            groups = self._build_account_groups(
                accounts_list,
                metrics["account_totals"],
                metrics["account_variances"],
            )

            final_queries = len(connection.queries) if settings.DEBUG else 0
            query_count = final_queries - initial_queries if settings.DEBUG else 0

            logger.info(
                "sidebar_data_built",
                user_id=user.id,
                account_count=len(accounts_list),
                grand_total=float(metrics["grand_total"]),
                query_count=query_count,
            )

            return {
                "grand_total": metrics["grand_total"],
                "account_totals": metrics["account_totals"],
                "account_variances": metrics["account_variances"],
                "accounts_by_group": groups,
                "query_count": query_count,
            }

        except Exception as e:
            logger.error(
                "sidebar_data_build_failed",
                user_id=user.id,
                error=str(e),
                exc_info=True,
            )
            return {
                "grand_total": Decimal("0.00"),
                "account_totals": {},
                "account_variances": {},
                "accounts_by_group": OrderedDict(),
                "query_count": 0,
            }

    def get_account_totals(self, user: Any) -> dict[int, Decimal]:
        """Get account totals using vectorized operation."""
        holdings_df = self.data_provider.get_holdings_df(user)
        if holdings_df.empty:
            return {}

        result: dict[int, Decimal] = (
            holdings_df.groupby("account_id")["value"]
            .sum()
            .apply(lambda x: Decimal(str(x)))
            .to_dict()
        )
        return result

    def get_portfolio_total(self, user: Any) -> Decimal:
        """Get total portfolio value."""
        account_totals = self.get_account_totals(user)
        return sum(account_totals.values(), Decimal("0.00"))

    def _build_account_groups(
        self,
        accounts: list[dict],
        totals: dict[int, Decimal],
        variances: dict[int, float],
    ) -> dict[str, dict]:
        """Build account groups structure for sidebar."""
        from portfolio.models import AccountGroup

        all_groups = AccountGroup.objects.all().order_by("sort_order", "name")

        # Initialize groups structure
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for g in all_groups:
            groups[g.name] = {
                "label": g.name,
                "total": Decimal("0.00"),
                "accounts": [],
            }

        # Add "Other" group for ungrouped accounts
        if "Other" not in groups:
            groups["Other"] = {
                "label": "Other",
                "total": Decimal("0.00"),
                "accounts": [],
            }

        for acc in accounts:
            acc_id = acc["id"]
            # Get group name from account type
            group_name = acc.get("account_type__group__name", "Other")

            if group_name not in groups:
                groups[group_name] = {
                    "label": group_name,
                    "total": Decimal("0.00"),
                    "accounts": [],
                }

            acc_total = totals.get(acc_id, Decimal("0.00"))

            groups[group_name]["accounts"].append(
                {
                    "id": acc_id,
                    "name": acc["name"],
                    "total": acc_total,
                    "absolute_deviation_pct": variances.get(acc_id, 0.0),
                    "institution": acc.get("institution__name", "Direct"),
                    "account_type": acc.get("account_type__label", "Unknown"),
                }
            )

            groups[group_name]["total"] += acc_total

        # Sort accounts within each group by total (descending)
        for group in groups.values():
            group["accounts"].sort(key=lambda x: x["total"], reverse=True)

        # Remove empty groups
        return OrderedDict((k, v) for k, v in groups.items() if v["accounts"])

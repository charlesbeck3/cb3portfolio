from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

import pandas as pd

from portfolio.models import (
    AccountType,
    AccountTypeStrategyAssignment,
    AssetClass,
    Portfolio,
    TargetAllocation,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.views.mixins import PortfolioContextMixin


class DashboardView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        assert user.is_authenticated



        # 2. Build Account Types with lightweight context
        account_types_qs = (
            AccountType.objects.filter(accounts__user=user)
            .distinct()
            .order_by("group__sort_order", "label")
        )

        assignments = (
            AccountTypeStrategyAssignment.objects.filter(
                user=user, account_type__in=account_types_qs
            )
            .select_related("account_type", "allocation_strategy")
            .all()
        )
        strategy_ids = [a.allocation_strategy_id for a in assignments]
        # Optimization: Fetch all needed TargetAllocations in one go
        strategy_allocations = (
            TargetAllocation.objects.filter(strategy_id__in=strategy_ids)
            .select_related("asset_class")
            .all()
        )

        strategy_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        for alloc in strategy_allocations:
            strategy_map[alloc.strategy_id][alloc.asset_class_id] = alloc.target_percent

        assignment_map: dict[int, dict[int, Decimal]] = {
            a.account_type_id: strategy_map.get(a.allocation_strategy_id, {}) for a in assignments
        }

        # Initialize Engine and Data
        portfolio = Portfolio.objects.filter(user=user).first()
        # Initialize Engine and Data
        portfolio = Portfolio.objects.filter(user=user).first()
        holdings_df = portfolio.to_dataframe() if portfolio else pd.DataFrame()

        engine = AllocationCalculationEngine()

        # Calculate Account Type Totals for "rich" objects
        # We can use the engine's internal methods or simple pandas sum
        if not holdings_df.empty:
            # Group by Account_Type and sum
            at_totals_df = holdings_df.groupby(level="Account_Type", axis=0).sum().sum(axis=1)
            at_totals_map = at_totals_df.to_dict()
            portfolio_total_value = Decimal(float(holdings_df.sum().sum()))
        else:
            at_totals_map = {}
            portfolio_total_value = Decimal("0.00")

        rich_account_types: list[Any] = []
        for at_obj in account_types_qs:
            at: Any = at_obj
            # at_totals_map key is the label (e.g. "Taxable")
            at.current_total_value = Decimal(float(at_totals_map.get(at.label, 0.0)))
            at.target_map = assignment_map.get(at.id, {})
            rich_account_types.append(at)

        context["account_types"] = rich_account_types

        cash_ac = AssetClass.objects.filter(name="Cash").first()
        context["cash_asset_class_id"] = cash_ac.id if cash_ac else None
        context["portfolio_total_value"] = portfolio_total_value

        # Use Engine for Allocation Rows
        context["allocation_rows_money"] = engine.calculate_dashboard_rows(
            holdings_df=holdings_df,
            account_types=rich_account_types,
            portfolio_total_value=portfolio_total_value,
            mode="dollar",
            cash_asset_class_id=context["cash_asset_class_id"],
        )
        context["allocation_rows_percent"] = engine.calculate_dashboard_rows(
            holdings_df=holdings_df,
            account_types=rich_account_types,
            portfolio_total_value=portfolio_total_value,
            mode="percent",
            cash_asset_class_id=context["cash_asset_class_id"],
        )


        # Legacy/Debug info (optional, can remove if we are confident)
        # Leaving minimal debug context if needed or removing entirely
        # The user asked to Simplify. Let's remove the extra heavy debug tables.

        return context

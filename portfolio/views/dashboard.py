from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from portfolio.models import AccountType, AccountTypeStrategyAssignment, AssetClass, TargetAllocation
from portfolio.presenters import AllocationTableBuilder
from portfolio.views.mixins import PortfolioContextMixin


class DashboardView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/index.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        assert user.is_authenticated

        # 1. Get Summary Data via shared services
        services = self.get_portfolio_services()
        summary_service = services["summary"]

        summary = summary_service.get_holdings_summary(user)
        context["summary"] = summary

        context.update(self.get_sidebar_context())

        # 2. Build Account Types with lightweight context
        account_types_qs = (
            AccountType.objects.filter(accounts__user=user)
            .distinct()
            .order_by("group__sort_order", "label")
        )

        assignments = (
            AccountTypeStrategyAssignment.objects.filter(user=user, account_type__in=account_types_qs)
            .select_related("account_type", "allocation_strategy")
            .all()
        )
        strategy_ids = [a.allocation_strategy_id for a in assignments]
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

        at_totals = summary.account_type_grand_totals
        rich_account_types: list[Any] = []
        for at_obj in account_types_qs:
            at: Any = at_obj
            at.current_total_value = at_totals.get(at.code, Decimal("0.00"))
            at.target_map = assignment_map.get(at.id, {})
            rich_account_types.append(at)

        context["account_types"] = rich_account_types

        cash_ac = AssetClass.objects.filter(name="Cash").first()
        context["cash_asset_class_id"] = cash_ac.id if cash_ac else None

        # Calculate 'Portfolio Total Value' for template usage
        context["portfolio_total_value"] = summary.grand_total

        builder = AllocationTableBuilder()
        context["allocation_rows_money"] = builder.build_rows(
            summary=summary,
            account_types=rich_account_types,
            portfolio_total_value=summary.grand_total,
            mode="money",
            cash_asset_class_id=context["cash_asset_class_id"],
        )
        context["allocation_rows_percent"] = builder.build_rows(
            summary=summary,
            account_types=rich_account_types,
            portfolio_total_value=summary.grand_total,
            mode="percent",
            cash_asset_class_id=context["cash_asset_class_id"],
        )

        return context

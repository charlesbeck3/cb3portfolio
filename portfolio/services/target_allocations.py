from __future__ import annotations

import contextlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, cast

from django.db import transaction

import pandas as pd

from portfolio.models import (
    Account,
    AccountType,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    AssetClass,
    TargetAllocation,
)
from portfolio.presenters import TargetAllocationTableBuilder
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from users.models import CustomUser


class TargetAllocationViewService:
    def build_context(self, *, user: CustomUser) -> dict[str, Any]:
        engine = AllocationCalculationEngine()

        defaults_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        overrides_map: dict[int, dict[int, Decimal]] = defaultdict(dict)

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
        assignment_by_at_id = {a.account_type_id: a for a in assignments}

        strategy_ids: set[int] = {a.allocation_strategy_id for a in assignments}

        accounts = (
            Account.objects.filter(user=user)
            .select_related("account_type", "allocation_strategy")
            .all()
        )
        {a.id: a for a in accounts}

        override_accounts = [a for a in accounts if a.allocation_strategy_id]
        strategy_ids.update(cast(int, a.allocation_strategy_id) for a in override_accounts)

        strategy_allocations = (
            TargetAllocation.objects.filter(strategy_id__in=strategy_ids)
            .select_related("asset_class")
            .all()
        )

        alloc_map: dict[int, dict[int, Decimal]] = defaultdict(dict)
        for alloc in strategy_allocations:
            alloc_map[alloc.strategy_id][alloc.asset_class_id] = alloc.target_percent

        for at_id, assignment in assignment_by_at_id.items():
            defaults_map[at_id] = alloc_map.get(assignment.allocation_strategy_id, {})

        for acc in override_accounts:
            overrides_map[acc.id] = alloc_map.get(cast(int, acc.allocation_strategy_id), {})

        # Fetch Portfolio and convert to DataFrame
        portfolio = accounts[0].portfolio if accounts else None
        holdings_df = pd.DataFrame()

        if portfolio:
            portfolios = list({acc.portfolio for acc in accounts if acc.portfolio})
            dfs = []
            for p in portfolios:
                dfs.append(p.to_dataframe())

            if dfs:
                holdings_df = pd.concat(dfs)

        # Calculate Allocations
        allocations = engine.calculate_allocations(holdings_df)

        account_totals: dict[int, Decimal] = {}
        at_values: dict[int, Decimal] = {}

        df_at = allocations.get("by_account_type")
        df_acc = allocations.get("by_account")

        # Handle MultiIndex for by_account (index is [Type, Cat, Name])
        if df_acc is not None and isinstance(df_acc.index, pd.MultiIndex):
            # Reset index to make accessing by Name easier, assuming Name is unique per user/portfolio context
            # or minimally we index by it.
            # We keep other columns if needed, but we mostly need values.
            # Level 2 is Account_Name.
            with contextlib.suppress(IndexError, ValueError):
                df_acc = df_acc.reset_index(level=[0, 1])

            # Update allocations dict so Builder receives normalized DF
            allocations['by_account'] = df_acc

        account_types = []
        for at_obj in account_types_qs:
            at: Any = at_obj
            at_accounts = [a for a in accounts if a.account_type_id == at.id]

            at_total = Decimal("0.00")
            if df_at is not None and at.label in df_at.index:
                dollar_cols = [c for c in df_at.columns if c.endswith("_dollars")]
                at_total = Decimal(float(df_at.loc[at.label, dollar_cols].sum()))

            at.current_total_value = at_total
            at.target_map = defaults_map.get(at.id, {})
            at_values[at.id] = at_total

            for acc in at_accounts:
                acc_total = Decimal("0.00")
                if df_acc is not None and acc.name in df_acc.index:
                     dollar_cols = [c for c in df_acc.columns if c.endswith("_dollars")]
                     # Could be Series or DataFrame if name partial match? Exact match on Index expected.
                     rows = df_acc.loc[acc.name, dollar_cols]
                     if isinstance(rows, pd.Series):
                         acc_total = Decimal(float(rows.sum()))
                     else:
                         # Ensure we sum scalar values if it's single row DF
                         acc_total = Decimal(float(rows.sum().sum())) # sum columns then rows?
                         # Usually distinct names, so single row.
                         pass

                acc.current_total_value = acc_total
                account_totals[acc.id] = acc_total
                acc.target_map = overrides_map.get(acc.id, {})

            if at.id in assignment_by_at_id:
                at.active_strategy_id = assignment_by_at_id[at.id].allocation_strategy_id
            else:
                at.active_strategy_id = None

            at.active_accounts = at_accounts
            account_types.append(at)

        # Build Metadata & Hierarchy
        ac_qs = AssetClass.objects.select_related('category__parent').all()
        ac_meta = {}
        hierarchy: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        sorted_acs = sorted(ac_qs, key=lambda x: (
            x.category.parent.sort_order if x.category.parent else x.category.sort_order,
            x.category.parent.code if x.category.parent else x.category.code,
            x.category.sort_order,
            x.category.code,
            x.name
        ))

        for ac in sorted_acs:
            if ac.category.parent:
                grp_code = ac.category.parent.code
                grp_label = ac.category.parent.label
            else:
                grp_code = ac.category.code
                grp_label = ac.category.label

            cat_code = ac.category.code
            cat_label = ac.category.label

            ac_meta[ac.name] = {
                'id': ac.id,
                'group_code': grp_code,
                'group_label': grp_label,
                'category_code': cat_code,
                'category_label': cat_label
            }

            hierarchy[grp_code][cat_code].append(ac.name)

        cash_ac = AssetClass.objects.filter(name="Cash").first()

        builder = TargetAllocationTableBuilder()

        # Determine total value
        total_val = Decimal("0.00")
        if allocations['portfolio_summary'] is not None and not allocations['portfolio_summary'].empty:
             val = allocations['portfolio_summary'].iloc[0].get('Total_Value')
             if val is not None:
                 total_val = Decimal(float(val))

        allocation_rows_percent = builder.build_rows(
            allocations=allocations,
            ac_meta=ac_meta,
            hierarchy=hierarchy,
            account_types=account_types,
            portfolio_total_value=total_val,
            mode="percent",
            cash_asset_class_id=cash_ac.id if cash_ac else None,
            account_targets={}
        )
        allocation_rows_money = builder.build_rows(
            allocations=allocations,
            ac_meta=ac_meta,
            hierarchy=hierarchy,
            account_types=account_types,
            portfolio_total_value=total_val,
            mode="dollar",
            cash_asset_class_id=cash_ac.id if cash_ac else None,
            account_targets={}
        )

        strategies = AllocationStrategy.objects.filter(user=user).order_by("name")

        class SimpleSummary:
            grand_total = total_val

        summary = SimpleSummary()

        return {
            "summary": summary,
            "account_types": account_types,
            "portfolio_total_value": summary.grand_total,
            "allocation_rows_percent": allocation_rows_percent,
            "allocation_rows_money": allocation_rows_money,
            "at_values": at_values,
            "account_totals": account_totals,
            "defaults_map": defaults_map,
            "cash_asset_class_id": cash_ac.id if cash_ac else None,
            "strategies": strategies,
        }

    def save_from_post(self, *, request: Any) -> tuple[bool, list[str]]:
        user = request.user
        if not user.is_authenticated:
            return False, ["Authentication required."]

        user = cast(Any, user)

        account_types = AccountType.objects.filter(accounts__user=user).distinct()
        accounts = Account.objects.filter(user=user)

        with transaction.atomic():
            # 1. Update Account Type Strategies
            for at in account_types:
                strategy_id_str = request.POST.get(f"strategy_at_{at.id}")

                # If "Select Strategy" (empty string) is chosen, we remove the assignment
                if not strategy_id_str:
                     AccountTypeStrategyAssignment.objects.filter(
                         user=user, account_type=at
                     ).delete()
                     continue

                try:
                    strategy_id = int(strategy_id_str)
                    strategy = AllocationStrategy.objects.get(id=strategy_id, user=user)

                    AccountTypeStrategyAssignment.objects.update_or_create(
                        user=user,
                        account_type=at,
                        defaults={"allocation_strategy": strategy},
                    )
                except (ValueError, AllocationStrategy.DoesNotExist):
                    # Invalid input or strategy doesn't exist/belong to user
                    pass

            # 2. Update Account Overrides
            for acc in accounts:
                strategy_id_str = request.POST.get(f"strategy_acc_{acc.id}")

                if not strategy_id_str:
                    if acc.allocation_strategy:
                        acc.allocation_strategy = None
                        acc.save(update_fields=["allocation_strategy"])
                    continue

                try:
                    strategy_id = int(strategy_id_str)
                    strategy = AllocationStrategy.objects.get(id=strategy_id, user=user)

                    if acc.allocation_strategy_id != strategy.id:
                        acc.allocation_strategy = strategy
                        acc.save(update_fields=["allocation_strategy"])
                except (ValueError, AllocationStrategy.DoesNotExist):
                     pass

        return True, []

import time
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portfolio.models import (
    Account,
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Holding,
    Institution,
    Portfolio,
    Security,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.services.allocation_presentation import AllocationPresentationFormatter

User = get_user_model()


class Command(BaseCommand):
    help = "Benchmark allocation performance with vectorized vs loop implementation."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Setting up large benchmark dataset...")
        user = User.objects.filter(username="benchmark_user").first()
        if not user:
            user = User.objects.create_user(username="benchmark_user")

        # Cleanup existing data for this user
        Portfolio.objects.filter(user=user).delete()

        # Create hierarchy
        n_categories = 5
        n_ac_per_cat = 5
        n_accounts = 20
        n_holdings_per_account = 20  # Total 400 holdings

        parent_cat = AssetClassCategory.objects.get_or_create(code="ROOT", label="Root")[0]
        categories = []
        for i in range(n_categories):
            cat = AssetClassCategory.objects.get_or_create(
                code=f"CAT_{i}", label=f"Category {i}", parent=parent_cat
            )[0]
            categories.append(cat)

        asset_classes = []
        for cat in categories:
            for j in range(n_ac_per_cat):
                ac = AssetClass.objects.get_or_create(name=f"AC_{cat.code}_{j}", category=cat)[0]
                asset_classes.append(ac)

        portfolio = Portfolio.objects.create(user=user, name="Benchmark Portfolio")
        inst = Institution.objects.get_or_create(name="Benchmark Inst")[0]
        ac_group = AccountGroup.objects.get_or_create(name="Benchmark Group")[0]
        ac_type = AccountType.objects.get_or_create(
            label="Benchmark Type", code="BMT", group=ac_group
        )[0]

        accounts = []
        for i in range(n_accounts):
            acc = Account.objects.create(
                user=user,
                name=f"Account {i}",
                portfolio=portfolio,
                account_type=ac_type,
                institution=inst,
            )
            accounts.append(acc)

        holdings = []
        for acc in accounts:
            for j in range(n_holdings_per_account):
                ac = asset_classes[(acc.id + j) % len(asset_classes)]
                sec = Security.objects.get_or_create(
                    ticker=f"SEC_{ac.id}_{j}", name=f"Security {j}", asset_class=ac
                )[0]
                holdings.append(
                    Holding(
                        account=acc,
                        security=sec,
                        shares=Decimal("100"),
                        current_price=Decimal("10.00"),
                    )
                )
        Holding.objects.bulk_create(holdings)

        self.stdout.write(f"Created {len(holdings)} holdings across {n_accounts} accounts.")

        engine = AllocationCalculationEngine()
        formatter = AllocationPresentationFormatter()

        # Benchmark Start
        self.stdout.write("\nRunning Vectorized Allocation Calculation...")
        start = time.time()
        df = engine.build_presentation_dataframe(user)
        aggregated = engine.aggregate_presentation_levels(df)
        ac_meta, _ = engine._get_asset_class_metadata(user)
        _, accounts_by_type = engine._get_account_metadata(user)
        target_strategies = engine._get_target_strategies(user)
        rows = formatter.format_presentation_rows(
            aggregated, accounts_by_type, target_strategies, mode="percent"
        )
        end = time.time()

        vectorized_time = end - start
        self.stdout.write(self.style.SUCCESS(f"Vectorized Total Time: {vectorized_time:.4f}s"))
        self.stdout.write(f"Total Rows Generated: {len(rows)}")

        self.stdout.write("\nBenchmark Complete.")

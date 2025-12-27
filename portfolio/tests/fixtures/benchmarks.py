"""
Benchmark fixtures for performance testing.

These create large-scale portfolio data for testing calculation performance
and detecting regressions.
"""

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest

from portfolio.models import (
    Account,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Holding,
    Institution,
    Portfolio,
    Security,
)

User = get_user_model()


@pytest.fixture
def large_portfolio_benchmark(base_system_data: Any, db: Any) -> dict[str, Any]:
    """
    Create a large benchmark portfolio for performance testing.

    Creates:
    - 5 asset class categories
    - 25 asset classes (5 per category)
    - 20 accounts
    - 400 holdings (20 per account)

    Total portfolio value: ~$400,000

    Returns:
        Dict with user, portfolio, accounts, and holdings counts
    """
    # Create benchmark user
    user = User.objects.create_user(
        username="benchmark_user",
        email="benchmark@example.com",
    )

    # Create portfolio
    portfolio = Portfolio.objects.create(user=user, name="Benchmark Portfolio")

    # Get or create institution
    institution = Institution.objects.get(name="Vanguard")

    # Create asset class hierarchy
    n_categories = 5
    n_ac_per_category = 5
    n_accounts = 20
    n_holdings_per_account = 20

    parent_category = AssetClassCategory.objects.filter(parent__isnull=True).first()
    if not parent_category:
        parent_category = AssetClassCategory.objects.create(code="ROOT", label="Root Category")

    categories = []
    for i in range(n_categories):
        cat, _ = AssetClassCategory.objects.get_or_create(
            code=f"BENCH_CAT_{i}",
            defaults={
                "label": f"Benchmark Category {i}",
                "parent": parent_category,
            },
        )
        categories.append(cat)

    # Create asset classes
    asset_classes = []
    for cat in categories:
        for j in range(n_ac_per_category):
            ac, _ = AssetClass.objects.get_or_create(
                name=f"Benchmark AC {cat.code}_{j}",
                defaults={"category": cat},
            )
            asset_classes.append(ac)

    # Create accounts
    account_type = AccountType.objects.first()
    accounts = []
    for i in range(n_accounts):
        account = Account.objects.create(
            user=user,
            portfolio=portfolio,
            name=f"Benchmark Account {i}",
            account_type=account_type,
            institution=institution,
        )
        accounts.append(account)

    # Create holdings
    holdings = []
    for account in accounts:
        for j in range(n_holdings_per_account):
            # Rotate through asset classes
            ac = asset_classes[(account.id * n_holdings_per_account + j) % len(asset_classes)]

            # Get or create security
            security, _ = Security.objects.get_or_create(
                ticker=f"BENCH_{ac.id}_{j}",
                defaults={
                    "name": f"Benchmark Security {ac.id}_{j}",
                    "asset_class": ac,
                },
            )

            holdings.append(
                Holding(
                    account=account,
                    security=security,
                    shares=Decimal("100.00"),
                    current_price=Decimal("50.00"),
                )
            )

    Holding.objects.bulk_create(holdings)

    return {
        "user": user,
        "portfolio": portfolio,
        "n_accounts": n_accounts,
        "n_holdings": len(holdings),
        "total_value": len(holdings) * Decimal("5000.00"),
    }


@pytest.fixture
def medium_portfolio_benchmark(base_system_data: Any, db: Any) -> dict[str, Any]:
    """
    Create a medium-sized portfolio for lighter performance testing.

    Creates:
    - 3 categories
    - 15 asset classes
    - 10 accounts
    - 100 holdings

    Returns:
        Dict with user, portfolio, accounts, and holdings counts
    """
    user = User.objects.create_user(
        username="medium_benchmark_user",
        email="medium@example.com",
    )

    portfolio = Portfolio.objects.create(user=user, name="Medium Benchmark")
    institution = Institution.objects.get(name="Vanguard")

    # Simplified version of large_portfolio_benchmark
    n_categories = 3
    n_ac_per_category = 5
    n_accounts = 10
    n_holdings_per_account = 10

    parent_category = AssetClassCategory.objects.filter(parent__isnull=True).first()

    categories = []
    for i in range(n_categories):
        cat, _ = AssetClassCategory.objects.get_or_create(
            code=f"MED_CAT_{i}",
            defaults={
                "label": f"Medium Category {i}",
                "parent": parent_category,
            },
        )
        categories.append(cat)

    asset_classes = []
    for cat in categories:
        for j in range(n_ac_per_category):
            ac, _ = AssetClass.objects.get_or_create(
                name=f"Medium AC {cat.code}_{j}",
                defaults={"category": cat},
            )
            asset_classes.append(ac)

    account_type = AccountType.objects.first()
    accounts = []
    for i in range(n_accounts):
        account = Account.objects.create(
            user=user,
            portfolio=portfolio,
            name=f"Medium Account {i}",
            account_type=account_type,
            institution=institution,
        )
        accounts.append(account)

    holdings = []
    for account in accounts:
        for j in range(n_holdings_per_account):
            ac = asset_classes[(account.id * n_holdings_per_account + j) % len(asset_classes)]

            security, _ = Security.objects.get_or_create(
                ticker=f"MED_{ac.id}_{j}",
                defaults={
                    "name": f"Medium Security {ac.id}_{j}",
                    "asset_class": ac,
                },
            )

            holdings.append(
                Holding(
                    account=account,
                    security=security,
                    shares=Decimal("50.00"),
                    current_price=Decimal("100.00"),
                )
            )

    Holding.objects.bulk_create(holdings)

    return {
        "user": user,
        "portfolio": portfolio,
        "n_accounts": n_accounts,
        "n_holdings": len(holdings),
        "total_value": len(holdings) * Decimal("5000.00"),
    }

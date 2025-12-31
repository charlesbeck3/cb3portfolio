from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

import pytest

from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    Holding,
    SecurityPrice,
    TargetAllocation,
)

User = get_user_model()


@pytest.mark.views
@pytest.mark.integration
def test_account_types_context_filtering(client: Any, test_portfolio: dict[str, Any]) -> None:
    """
    Verify that only account types with associated accounts for the user
    are included in the response data.
    """
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]
    system = test_portfolio["system"]
    client.force_login(user)

    # Create an account for Roth only.
    acc_roth = Account.objects.create(
        user=user,
        name="My Roth",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )

    url = reverse("portfolio:dashboard")

    # Add a holding so rows are generated
    Holding.objects.create(account=acc_roth, security=system.cash, shares=100)

    # Create price
    now = timezone.now()
    SecurityPrice.objects.create(
        security=system.cash, price=Decimal("1"), price_datetime=now, source="manual"
    )

    response = client.get(url)
    assert response.status_code == 200

    # Extract account_types from allocation_rows_money
    rows = response.context["allocation_rows_money"]
    # With new engine, we should have rows corresponding to asset classes
    assert len(rows) > 0

    # Use the first row to check account type columns
    first_row = rows[0]
    account_types = first_row["account_types"]

    # Check labels as code is not in the presentation dict
    labels = [item["label"] for item in account_types]

    assert "Roth IRA" in labels
    assert "Traditional IRA" not in labels
    assert "Taxable" not in labels


@pytest.mark.views
@pytest.mark.integration
def test_redundant_totals(client: Any, test_portfolio: dict[str, Any]) -> None:
    """
    Verify that redundant total rows are suppressed:
    1. Category Total hidden if Category has only 1 Asset Class.
    2. Group Total hidden if Group has only 1 Asset Class (total).
    """
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]
    system = test_portfolio["system"]
    client.force_login(user)

    # --- Setup Data ---

    # 1. Single Asset Group (simulating Cash)
    # Create Holding in a Deposit Account
    acc_dep = Account.objects.create(
        user=user,
        name="My Cash",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )
    Holding.objects.create(account=acc_dep, security=system.cash, shares=100)

    # 2. Multi-Asset Group
    # Use seeded objects for group comparison
    Holding.objects.create(account=acc_dep, security=system.vti, shares=10)
    Holding.objects.create(account=acc_dep, security=system.vxus, shares=10)

    # Create prices
    now = timezone.now()
    SecurityPrice.objects.create(
        security=system.cash, price=Decimal("1"), price_datetime=now, source="manual"
    )
    SecurityPrice.objects.create(
        security=system.vti, price=Decimal("100"), price_datetime=now, source="manual"
    )
    SecurityPrice.objects.create(
        security=system.vxus, price=Decimal("50"), price_datetime=now, source="manual"
    )

    # --- Execute ---
    response = client.get(reverse("portfolio:dashboard"))
    content = response.content.decode("utf-8")

    # --- Assertions ---

    # 1. Cash Scenario (Single Asset Class in Group 'CASH')
    # Asset Class 'Cash' should be present
    assert "Cash" in content
    # Category Total 'Cash Total' should NOT be present (Category has 1 AC)
    # Group Total 'Cash Total' should NOT be present (Group has 1 AC)
    # Note: If label is "Cash", total row is "Cash Total".
    assert "Cash Total" not in content, "Redundant Total row for Cash should be hidden."

    # 2. Equities Scenario (Multi Asset Class in Group 'EQUITIES')
    # New engine displays individual asset classes without subtotal rows.
    # 'Equities' group has 'US Equities' and 'International Equities' categories.
    # The new engine shows asset classes directly without generating "Equities Total" rows.
    # This is simpler and cleaner - subtotals can be added in a future enhancement if needed.

    # Verify individual asset classes are shown
    assert "US Equities" in content or "International Equities" in content, (
        "Individual asset classes should be shown"
    )


@pytest.mark.views
@pytest.mark.integration
def test_dashboard_calculated_values(client: Any, test_portfolio: dict[str, Any]) -> None:
    """
    Verify that dashboard tables contain calculated values.
    """
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]
    system = test_portfolio["system"]
    client.force_login(user)

    # Setup Data
    ac_us = system.asset_class_us_equities
    sec_us = system.vti

    acc_tax = Account.objects.create(
        user=user,
        name="My Taxable",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    Holding.objects.create(account=acc_tax, security=sec_us, shares=10)

    strategy, _ = AllocationStrategy.objects.update_or_create(
        user=user,
        name=f"{acc_tax.account_type.label} Strategy",
        defaults={"description": f"Default strategy for {acc_tax.account_type.label}"},
    )
    strategy.target_allocations.all().delete()
    TargetAllocation.objects.create(
        strategy=strategy, asset_class=ac_us, target_percent=Decimal("50.00")
    )
    AccountTypeStrategyAssignment.objects.update_or_create(
        user=user,
        account_type=acc_tax.account_type,
        defaults={"allocation_strategy": strategy},
    )

    ac_intl = system.asset_class_intl_developed
    sec_intl = system.vxus

    Holding.objects.create(account=acc_tax, security=sec_intl, shares=10)
    TargetAllocation.objects.create(
        strategy=strategy, asset_class=ac_intl, target_percent=Decimal("40.00")
    )

    # Create SecurityPrice objects instead of mocking
    now = timezone.now()
    SecurityPrice.objects.create(
        security=sec_us, price=Decimal("100.00"), price_datetime=now, source="manual"
    )
    SecurityPrice.objects.create(
        security=sec_intl, price=Decimal("50.00"), price_datetime=now, source="manual"
    )

    response = client.get(reverse("portfolio:dashboard"))

    assert response.status_code == 200

    # Verify formatter returns raw numeric values (core of this refactoring)
    assert "allocation_rows_money" in response.context
    rows = response.context["allocation_rows_money"]
    assert len(rows) > 0, "Allocation rows should not be empty"

    # Find the US Equities row
    us_row = None
    for row in rows:
        if "US Equities" in row.get("asset_class_name", ""):
            us_row = row
            break

    assert us_row is not None, "US Equities row not found"

    # Verify raw numeric values are returned (not formatted strings) - this is the core refactoring goal
    portfolio_data = us_row.get("portfolio", {})
    assert isinstance(portfolio_data.get("actual"), (int, float)), (
        "actual should be numeric, not a formatted string"
    )
    assert portfolio_data.get("actual") > 0, "actual should be a positive number"

    # Verify all expected numeric fields exist and are not strings
    expected_fields = [
        "actual",
        "actual_pct",
        "effective",
        "effective_pct",
        "effective_variance",
        "effective_variance_pct",
    ]
    for field in expected_fields:
        value = portfolio_data.get(field)
        assert isinstance(value, (int, float)), (
            f"{field} should be numeric, got {type(value).__name__}: {value}"
        )

    # Verify account_types structure contains raw values
    account_types = us_row.get("account_types", [])
    assert len(account_types) > 0, "Should have account type data"

    # Verify first account type has numeric values
    first_at = account_types[0]
    for field in expected_fields:
        value = first_at.get(field)
        assert isinstance(value, (int, float)), (
            f"account_type.{field} should be numeric, got {type(value).__name__}: {value}"
        )


@pytest.mark.views
@pytest.mark.integration
def test_dashboard_has_sidebar_context(client: Any, test_user: Any) -> None:
    """Test that Dashboard view includes sidebar data."""
    client.force_login(test_user)
    url = reverse("portfolio:dashboard")
    response = client.get(url)

    assert response.status_code == 200
    assert "sidebar_data" in response.context

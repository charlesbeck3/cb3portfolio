from typing import Any

from django.contrib.auth import get_user_model

import pytest

from portfolio.models import Account, AccountGroup, AccountType

User = get_user_model()


@pytest.mark.integration
def test_account_grouping(client: Any, test_portfolio: dict[str, Any]) -> None:
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]
    system = test_portfolio["system"]
    client.force_login(user)

    # Create basic account instances for testing grouping logic
    # Using types from system data:
    # type_roth (Retirement), type_trad (Retirement),
    # type_taxable (Investments)

    Account.objects.create(
        user=user,
        name="Roth",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )
    Account.objects.create(
        user=user,
        name="Trad",
        portfolio=portfolio,
        account_type=system.type_trad,
        institution=system.institution,
    )
    Account.objects.create(
        user=user,
        name="Taxable",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    # Create a Savings account type and account for Deposit group
    # Note: system.group_deposits exists in seeder
    type_savings = AccountType.objects.create(
        code="SAVINGS", label="Savings", group=system.group_deposits, tax_treatment="TAXABLE"
    )
    Account.objects.create(
        user=user,
        name="Savings",
        portfolio=portfolio,
        account_type=type_savings,
        institution=system.institution,
    )

    # Create a Mystery group and type
    mystery_group = AccountGroup.objects.create(name="Mystery Group", sort_order=99)
    mystery_type = AccountType.objects.create(
        code="MYSTERY", label="Mystery", group=mystery_group, tax_treatment="TAXABLE"
    )

    Account.objects.create(
        user=user,
        name="Mystery Account",
        portfolio=portfolio,
        account_type=mystery_type,
        institution=system.institution,
    )

    # Verify using Dashboard View
    # Since logic is in get_sidebar_context mixin used by Dashboard

    response = client.get("/")  # Dashboard URL
    assert response.status_code == 200

    sidebar_data = response.context["sidebar_data"]
    groups = sidebar_data["groups"]

    # Check Retirement
    assert "Retirement" in groups
    assert len(groups["Retirement"]["accounts"]) == 2

    # Check Investments
    assert "Investments" in groups
    assert len(groups["Investments"]["accounts"]) == 1
    assert groups["Investments"]["accounts"][0]["name"] == "Taxable"

    # Check Deposits
    assert "Deposits" in groups
    assert len(groups["Deposits"]["accounts"]) == 1
    assert groups["Deposits"]["accounts"][0]["name"] == "Savings"

    # Check Mystery Group
    assert "Mystery Group" in groups
    assert len(groups["Mystery Group"]["accounts"]) == 1
    assert groups["Mystery Group"]["accounts"][0]["name"] == "Mystery Account"

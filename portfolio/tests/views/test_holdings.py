from typing import Any

from django.contrib.auth import get_user_model
from django.urls import reverse

import pytest

from portfolio.models import Account

User = get_user_model()


@pytest.mark.views
@pytest.mark.integration
def test_holdings_view(client: Any, test_portfolio: dict[str, Any]) -> None:
    user = test_portfolio["user"]

    # We need an account for the user so default redirect doesn't happen or empty state works
    # Actually holdings view usually works empty.

    client.force_login(user)

    url = reverse("portfolio:holdings")
    response = client.get(url)
    assert response.status_code == 200
    # assertTemplateUsed is django implementation detail, check context or content
    assert "holdings_rows" in response.context
    assert "sidebar_data" in response.context
    # Account should not be in context
    assert "account" not in response.context


@pytest.mark.views
@pytest.mark.integration
def test_holdings_view_with_account(client: Any, test_portfolio: dict[str, Any]) -> None:
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]
    system = test_portfolio["system"]
    client.force_login(user)

    account = Account.objects.create(
        user=user,
        name="My Roth",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )

    url = reverse("portfolio:account_holdings", args=[account.id])
    response = client.get(url)
    assert response.status_code == 200
    assert "account" in response.context
    assert response.context["account"] == account


@pytest.mark.views
@pytest.mark.integration
def test_holdings_view_invalid_account(client: Any, test_user: Any) -> None:
    client.force_login(test_user)
    # Should suppress DoesNotExist
    url = reverse("portfolio:account_holdings", args=[99999])
    response = client.get(url)
    assert response.status_code == 200
    assert "account" not in response.context

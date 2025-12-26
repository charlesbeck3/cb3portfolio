from typing import Any

from django.contrib.auth import get_user_model
from django.urls import reverse

import pytest

from portfolio.models import Account

User = get_user_model()


@pytest.mark.views
@pytest.mark.integration
def test_target_allocations_has_sidebar_context(
    client: Any, test_portfolio: dict[str, Any]
) -> None:
    """Test that Target Allocations view includes sidebar data."""
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]
    system = test_portfolio["system"]
    client.force_login(user)

    # Create an account so groups are populated
    Account.objects.create(
        user=user,
        name="My Roth",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )

    url = reverse("portfolio:target_allocations")
    response = client.get(url)

    assert response.status_code == 200
    assert "sidebar_data" in response.context, "sidebar_data missing from context"
    assert response.context["sidebar_data"]["groups"] is not None, "Sidebar groups missing"
    assert len(response.context["sidebar_data"]["groups"]) > 0, "Sidebar should have groups"

from decimal import Decimal
from typing import Any

import pytest

from portfolio.models import RebalancingRecommendation


@pytest.mark.models
@pytest.mark.integration
def test_create_recommendation(simple_holdings: dict[str, Any]) -> None:
    """Test creating a rebalancing recommendation."""
    account = simple_holdings["account"]
    system = simple_holdings["system"]
    security = system.vti

    rec = RebalancingRecommendation.objects.create(
        account=account,
        security=security,
        action="BUY",
        shares=Decimal("10.00"),
        estimated_amount=Decimal("1600.00"),
        reason="Underweight",
    )
    assert rec.action == "BUY"
    assert str(rec) == f"BUY 10.00 VTI in {account.name}"

from decimal import Decimal
from typing import Any

import pytest

from portfolio.models import AssetClass


@pytest.mark.models
@pytest.mark.integration
def test_create_asset_class(base_system_data: Any) -> None:
    """Test creating an asset class."""
    us_equities = base_system_data.cat_us_eq
    ac = AssetClass.objects.create(
        name="US Stocks Test", category=us_equities, expected_return=Decimal("0.08")
    )
    assert ac.name == "US Stocks Test"
    assert ac.expected_return == Decimal("0.08")
    assert str(ac) == "US Stocks Test"

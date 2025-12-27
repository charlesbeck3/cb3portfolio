from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

import pytest

from portfolio.models import (
    Account,
    AllocationStrategy,
    AssetClass,
    Holding,
    Portfolio,
    Security,
    TargetAllocation,
)


@pytest.mark.models
@pytest.mark.integration
class TestPortfolio:
    def test_to_dataframe_structure(self, test_portfolio: dict[str, Any]) -> None:
        """Portfolio DataFrame has correct MultiIndex structure."""
        portfolio = test_portfolio["portfolio"]
        df = portfolio.to_dataframe()
        assert df.index.names == ["Account_Type", "Account_Category", "Account_Name", "Account_ID"]
        assert df.columns.names == ["Asset_Class", "Asset_Category", "Security"]
        # Empty because no holdings yet in basic fixture
        # But let's verify structure even if empty
        assert df.empty

    def test_to_dataframe_values(self, test_portfolio: dict[str, Any]) -> None:
        """Portfolio DataFrame has correct values."""
        system = test_portfolio["system"]
        portfolio = test_portfolio["portfolio"]
        user = test_portfolio["user"]

        # Setup specific data for this test
        us_stocks = AssetClass.objects.create(name="US Stk", category=system.cat_us_eq)
        bonds = AssetClass.objects.create(name="Bonds", category=system.cat_fi)

        vti = Security.objects.create(
            ticker="VTI_TEST", name="Vanguard Stock", asset_class=us_stocks
        )
        bnd = Security.objects.create(ticker="BND_TEST", name="Vanguard Bond", asset_class=bonds)

        account = Account.objects.create(
            name="Test Account",
            account_type=system.type_taxable,
            portfolio=portfolio,
            user=user,
            institution=system.institution,
        )
        Holding.objects.create(
            account=account,
            security=vti,
            shares=Decimal("50"),
            current_price=Decimal("100.00"),
        )
        Holding.objects.create(
            account=account,
            security=bnd,
            shares=Decimal("100"),
            current_price=Decimal("50.00"),
        )

        df = portfolio.to_dataframe()
        assert not df.empty
        assert ("US Stk", "US Equities", "VTI_TEST") in df.columns
        assert ("Bonds", "Fixed Income", "BND_TEST") in df.columns

        # Value check: 50 * 100 = 5000
        # Index now includes Account_ID, so we need to match on all 4 levels
        val = df.loc[
            ("Taxable", "Investments", "Test Account", account.id),
            ("US Stk", "US Equities", "VTI_TEST"),
        ]
        assert val == 5000.0

    def test_empty_portfolio_dataframe(self, test_user: Any) -> None:
        """Empty portfolio returns empty DataFrame with correct structure."""
        empty = Portfolio.objects.create(name="Empty", user=test_user)
        df = empty.to_dataframe()
        assert df.empty
        assert df.index.names == ["Account_Type", "Account_Category", "Account_Name", "Account_ID"]


@pytest.mark.models
@pytest.mark.integration
def test_portfolio_with_invalid_strategy_validation(test_user: Any, base_system_data: Any) -> None:
    """Test that portfolio validates its assigned strategy."""
    system = base_system_data

    # Create a strategy with allocations that don't sum to 100%
    strategy = AllocationStrategy.objects.create(user=test_user, name="Invalid Strategy")
    asset_class, _ = AssetClass.objects.get_or_create(
        name="US Equities", defaults={"category": system.cat_us_eq}
    )

    # Manually create allocations that sum to 90% (bypassing save_allocations)
    TargetAllocation.objects.create(
        strategy=strategy,
        asset_class=asset_class,
        target_percent=Decimal("90.00"),
    )

    # Create portfolio
    portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")

    # Assign the invalid strategy
    portfolio.allocation_strategy = strategy

    # Saving should raise validation error
    with pytest.raises(ValidationError) as exc_info:
        portfolio.save()

    assert "allocation_strategy" in exc_info.value.message_dict
    assert "100" in str(exc_info.value)

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

import pytest

from portfolio.models import (
    Account,
    AccountType,
    AllocationStrategy,
    AssetClass,
    Holding,
    Portfolio,
    RebalancingRecommendation,
    Security,
    TargetAllocation,
)

User = get_user_model()


@pytest.mark.models
@pytest.mark.integration
def test_account_type_to_dataframe(test_portfolio: dict[str, Any]) -> None:
    """AccountType DataFrame aggregates multiple accounts."""
    system = test_portfolio["system"]
    portfolio = test_portfolio["portfolio"]
    user = test_portfolio["user"]
    institution = system.institution
    type_obj = system.type_taxable

    # Use system asset class
    ac_us = system.cat_us_eq.asset_classes.create(name="US Stk Ty")
    sec = Security.objects.create(ticker="VTI_TY", asset_class=ac_us)

    acc1 = Account.objects.create(
        name="Acc 1",
        account_type=type_obj,
        portfolio=portfolio,
        user=user,
        institution=institution,
    )
    acc2 = Account.objects.create(
        name="Acc 2",
        account_type=type_obj,
        portfolio=portfolio,
        user=user,
        institution=institution,
    )

    Holding.objects.create(account=acc1, security=sec, shares=10, current_price=100)
    Holding.objects.create(account=acc2, security=sec, shares=20, current_price=100)

    df = type_obj.to_dataframe()
    assert len(df) == 2
    # Index is now MultiIndex with (Type, Category, Name, ID)
    # Check that account names appear in the index
    account_names = [idx[2] for idx in df.index]  # Name is at position 2
    assert "Acc 1" in account_names
    assert "Acc 2" in account_names


@pytest.mark.models
@pytest.mark.integration
def test_account_type_code_validation(base_system_data: Any) -> None:
    """Test that only valid account type codes can be created."""
    system = base_system_data

    # Valid account type should work (using HSA which may not exist yet)
    valid_type = AccountType(
        code=AccountType.CODE_HSA,
        label="Test HSA",
        group=system.group_retirement,
        tax_treatment=AccountType.TAX_FREE,
    )
    # Check if it already exists
    if not AccountType.objects.filter(code=AccountType.CODE_HSA).exists():
        valid_type.full_clean()  # Should not raise
        valid_type.save()
        assert valid_type.code == AccountType.CODE_HSA

    # Invalid account type should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        invalid_type = AccountType(
            code="INVALID_CODE",
            label="Invalid Type",
            group=system.group_retirement,
            tax_treatment=AccountType.TAXABLE,
        )
        invalid_type.full_clean()

    assert "code" in exc_info.value.message_dict
    assert "INVALID_CODE" in str(exc_info.value)


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
def test_create_asset_class(base_system_data: Any) -> None:
    """Test creating an asset class."""
    us_equities = base_system_data.cat_us_eq
    ac = AssetClass.objects.create(
        name="US Stocks Test", category=us_equities, expected_return=Decimal("0.08")
    )
    assert ac.name == "US Stocks Test"
    assert ac.expected_return == Decimal("0.08")
    assert str(ac) == "US Stocks Test"


@pytest.mark.models
@pytest.mark.integration
class TestAccount:
    def test_create_account(self, test_portfolio: dict[str, Any]) -> None:
        """Test creating an account."""
        system = test_portfolio["system"]
        account = Account.objects.create(
            user=test_portfolio["user"],
            name="Roth IRA",
            portfolio=test_portfolio["portfolio"],
            account_type=system.type_roth,
            institution=system.institution,
        )
        assert account.name == "Roth IRA"
        assert str(account) == "Roth IRA (testuser)"

    def test_tax_treatment_property(self, base_system_data: Any) -> None:
        """Test tax_treatment property derivation."""
        system = base_system_data

        roth = Account(account_type=system.type_roth)
        assert roth.tax_treatment == "TAX_FREE"

        trad = Account(account_type=system.type_trad)
        assert trad.tax_treatment == "TAX_DEFERRED"

        k401 = Account(account_type=system.type_401k)
        assert k401.tax_treatment == "TAX_DEFERRED"

        taxable = Account(account_type=system.type_taxable)
        assert taxable.tax_treatment == "TAXABLE"

    def test_is_tax_advantaged_property(self, base_system_data: Any) -> None:
        """Test is_tax_advantaged property."""
        system = base_system_data

        roth = Account(account_type=system.type_roth)
        assert roth.is_tax_advantaged is True

        trad = Account(account_type=system.type_trad)
        assert trad.is_tax_advantaged is True

        taxable = Account(account_type=system.type_taxable)
        assert taxable.is_tax_advantaged is False

    def test_total_value(self, test_portfolio: dict[str, Any]) -> None:
        system = test_portfolio["system"]
        account = Account.objects.create(
            user=test_portfolio["user"],
            name="Roth IRA",
            portfolio=test_portfolio["portfolio"],
            account_type=system.type_roth,
            institution=system.institution,
        )
        asset_class = AssetClass.objects.create(
            name="US Stocks Val",
            category=system.cat_us_eq,
        )
        security = Security.objects.create(ticker="VTI_VAL", asset_class=asset_class)

        Holding.objects.create(
            account=account,
            security=security,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )
        # 10 * 100 = 1000
        assert account.total_value() == Decimal("1000")

    def test_holdings_by_asset_class(self, test_portfolio: dict[str, Any]) -> None:
        system = test_portfolio["system"]
        account = Account.objects.create(
            user=test_portfolio["user"],
            name="Roth IRA",
            portfolio=test_portfolio["portfolio"],
            account_type=system.type_roth,
            institution=system.institution,
        )
        us_stocks = AssetClass.objects.create(
            name="US Stocks HAC",
            category=system.cat_us_eq,
        )
        bonds = AssetClass.objects.create(
            name="Bonds HAC",
            category=system.cat_us_eq,
        )
        vti = Security.objects.create(ticker="VTI_HAC", asset_class=us_stocks)
        bnd = Security.objects.create(ticker="BND_HAC", asset_class=bonds)

        Holding.objects.create(
            account=account,
            security=vti,
            shares=Decimal("2"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=account,
            security=bnd,
            shares=Decimal("4"),
            current_price=Decimal("50"),
        )

        by_ac = account.holdings_by_asset_class()
        assert by_ac["US Stocks HAC"] == Decimal("200")
        assert by_ac["Bonds HAC"] == Decimal("200")

    def test_calculate_deviation(self, test_portfolio: dict[str, Any]) -> None:
        system = test_portfolio["system"]
        account = Account.objects.create(
            user=test_portfolio["user"],
            name="Roth IRA",
            portfolio=test_portfolio["portfolio"],
            account_type=system.type_roth,
            institution=system.institution,
        )
        us_stocks = AssetClass.objects.create(
            name="US Stocks Dev",
            category=system.cat_us_eq,
        )
        bonds = AssetClass.objects.create(
            name="Bonds Dev",
            category=system.cat_us_eq,
        )
        vti = Security.objects.create(ticker="VTI_DEV", asset_class=us_stocks)
        bnd = Security.objects.create(ticker="BND_DEV", asset_class=bonds)

        # Current: 600 stocks, 400 bonds, total 1000
        Holding.objects.create(
            account=account,
            security=vti,
            shares=Decimal("6"),
            current_price=Decimal("100"),
        )
        Holding.objects.create(
            account=account,
            security=bnd,
            shares=Decimal("4"),
            current_price=Decimal("100"),
        )

        # Target: 50/50 -> 500 each
        targets = {"US Stocks Dev": Decimal("50"), "Bonds Dev": Decimal("50")}
        deviation = account.calculate_deviation(targets)
        # |600-500| + |400-500| = 200
        assert deviation == Decimal("200")

    def test_to_dataframe(self, test_portfolio: dict[str, Any]) -> None:
        """Account DataFrame has single row."""
        system = test_portfolio["system"]

        ac_us = AssetClass.objects.create(name="US Stk Ac", category=system.cat_us_eq)
        sec = Security.objects.create(ticker="VTI_AC", asset_class=ac_us)

        account = Account.objects.create(
            user=test_portfolio["user"],
            name="My Solitary Account",
            portfolio=test_portfolio["portfolio"],
            account_type=system.type_roth,
            institution=system.institution,
        )
        Holding.objects.create(
            account=account, security=sec, shares=Decimal("10"), current_price=Decimal("100")
        )

        df = account.to_dataframe()
        assert len(df) == 1
        # Index is now MultiIndex with (Type, Category, Name, ID)
        expected_index = ("Roth IRA", "Retirement", "My Solitary Account", account.id)
        assert df.index[0] == expected_index
        val = df.loc[expected_index, ("US Stk Ac", "US Equities", "VTI_AC")]
        assert val == 1000.0


@pytest.mark.models
@pytest.mark.integration
def test_create_security(base_system_data: Any) -> None:
    """Test creating a security."""
    system = base_system_data
    asset_class = AssetClass.objects.create(
        name="US Stocks Sec",
        category=system.cat_us_eq,
    )
    security = Security.objects.create(
        ticker="VTI_SEC", asset_class=asset_class, name="Vanguard Stock"
    )
    assert security.ticker == "VTI_SEC"
    assert str(security) == "VTI_SEC - Vanguard Stock"


@pytest.mark.models
@pytest.mark.integration
class TestHolding:
    def test_create_holding(self, simple_holdings: dict[str, Any]) -> None:
        """Test creating a holding."""
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        # Create a new holding
        holding = Holding.objects.create(
            account=account,
            security=system.vxus,  # Use different security
            shares=Decimal("10.5000"),
            current_price=Decimal("210.00"),
        )
        assert holding.shares == Decimal("10.5000")
        assert str(holding) == f"VXUS in {account.name} (10.5000 shares)"

    def test_market_value_with_price(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]
        holding = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )
        assert holding.market_value == Decimal("1000")

    def test_market_value_without_price(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]
        holding = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("10"),
            current_price=None,
        )
        assert holding.market_value == Decimal("0.00")

    def test_has_price_property(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        holding_with_price = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("1"),
            current_price=Decimal("50"),
        )
        assert holding_with_price.has_price

        holding_without_price = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("1"),
            current_price=None,
        )
        assert not holding_without_price.has_price

    def test_update_price(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        holding = Holding.objects.create(
            account=account,
            security=system.vxus,
            shares=Decimal("5"),
            current_price=Decimal("10"),
        )
        holding.update_price(Decimal("20"))
        holding.refresh_from_db()
        assert holding.current_price == Decimal("20")

    def test_calculate_target_value_and_variance(self, simple_holdings: dict[str, Any]) -> None:
        account = simple_holdings["account"]
        system = simple_holdings["system"]

        holding = Holding(
            account=account,
            security=system.vti,
            shares=Decimal("10"),
            current_price=Decimal("100"),
        )

        account_total = Decimal("10000")
        target_pct = Decimal("25")
        target_value = holding.calculate_target_value(account_total, target_pct)
        assert target_value == Decimal("2500")

        # Current value: 1000, Target: 2500 -> variance: -1500 (underweight)
        variance = holding.calculate_variance(target_value)
        assert variance == Decimal("1000") - Decimal("2500")


@pytest.mark.models
@pytest.mark.integration
class TestTargetAllocation:
    def test_create_target_allocation(self, test_user: Any, base_system_data: Any) -> None:
        """Test creating a target allocation."""
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        asset_class = AssetClass.objects.create(
            name="US Stocks TA",
            category=system.cat_us_eq,
        )

        target = TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=asset_class,
            target_percent=Decimal("40.00"),
        )
        assert target.target_percent == Decimal("40.00")
        assert str(target) == f"{strategy.name}: {asset_class.name} - 40.00%"

    def test_target_allocation_isolation(self, test_user: Any, base_system_data: Any) -> None:
        """Test that different users can have their own allocations."""
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy 1")
        asset_class = AssetClass.objects.create(
            name="US Stocks Iso",
            category=system.cat_us_eq,
        )

        # User 1 allocation
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=asset_class,
            target_percent=Decimal("40.00"),
        )

        # User 2 allocation
        user2 = User.objects.create_user(username="otheruser", password="password")
        strategy2 = AllocationStrategy.objects.create(user=user2, name="Test Strategy 2")
        target2 = TargetAllocation.objects.create(
            strategy=strategy2,
            asset_class=asset_class,
            target_percent=Decimal("60.00"),
        )

        # Count total
        assert TargetAllocation.objects.filter(asset_class=asset_class).count() == 2
        assert target2.strategy.user.username == "otheruser"
        assert target2.target_percent == Decimal("60.00")

    def test_target_value_for(self, test_user: Any, base_system_data: Any) -> None:
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        asset_class = AssetClass.objects.create(name="US Stocks ValFor", category=system.cat_us_eq)

        allocation = TargetAllocation(
            strategy=strategy,
            asset_class=asset_class,
            target_percent=Decimal("25"),
        )
        assert allocation.target_value_for(Decimal("10000")) == Decimal("2500")

    def test_validate_allocation_set_valid(self, test_user: Any, base_system_data: Any) -> None:
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        ac1 = AssetClass.objects.create(name="AC1", category=system.cat_us_eq)
        ac2 = AssetClass.objects.create(name="AC2", category=system.cat_us_eq)

        allocations = [
            TargetAllocation(
                strategy=strategy,
                asset_class=ac1,
                target_percent=Decimal("60"),
            ),
            TargetAllocation(
                strategy=strategy,
                asset_class=ac2,
                target_percent=Decimal("40"),
            ),
        ]
        ok, msg = TargetAllocation.validate_allocation_set(allocations)
        assert ok
        assert msg == ""

    def test_validate_allocation_set_exceeds_100(
        self, test_user: Any, base_system_data: Any
    ) -> None:
        system = base_system_data
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
        ac1 = AssetClass.objects.create(name="AC1", category=system.cat_us_eq)

        allocations = [
            TargetAllocation(
                strategy=strategy,
                asset_class=ac1,
                target_percent=Decimal("60"),
            ),
            TargetAllocation(
                strategy=strategy,
                asset_class=ac1,  # Same or diff doesn't matter for this test logic usually, but let's assume same strategy list
                target_percent=Decimal("50"),
            ),
        ]
        ok, msg = TargetAllocation.validate_allocation_set(allocations)
        assert not ok
        assert "110" in msg


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


# ============================================================================
# Phase 2: Target Allocation Validation Tests
# ============================================================================


@pytest.mark.models
@pytest.mark.integration
def test_target_allocation_negative_validation(test_user: Any, base_system_data: Any) -> None:
    """Test that negative allocations are rejected."""
    system = base_system_data
    strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
    asset_class = AssetClass.objects.create(name="US Stocks", category=system.cat_us_eq)

    allocation = TargetAllocation(
        strategy=strategy,
        asset_class=asset_class,
        target_percent=Decimal("-10.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        allocation.full_clean()

    assert "target_percent" in exc_info.value.message_dict
    assert "negative" in str(exc_info.value).lower()


@pytest.mark.models
@pytest.mark.integration
def test_target_allocation_over_100_validation(test_user: Any, base_system_data: Any) -> None:
    """Test that allocations over 100% are rejected."""
    system = base_system_data
    strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")
    asset_class = AssetClass.objects.create(name="US Stocks", category=system.cat_us_eq)

    allocation = TargetAllocation(
        strategy=strategy,
        asset_class=asset_class,
        target_percent=Decimal("150.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        allocation.full_clean()

    assert "target_percent" in exc_info.value.message_dict
    assert "100" in str(exc_info.value)


@pytest.mark.models
@pytest.mark.integration
def test_portfolio_with_invalid_strategy_validation(test_user: Any, base_system_data: Any) -> None:
    """Test that portfolio validates its assigned strategy."""
    system = base_system_data

    # Create a strategy with allocations that don't sum to 100%
    strategy = AllocationStrategy.objects.create(user=test_user, name="Invalid Strategy")
    asset_class = AssetClass.objects.create(name="US Stocks", category=system.cat_us_eq)

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

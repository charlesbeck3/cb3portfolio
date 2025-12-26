from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

import pytest

from portfolio.models import Account, AccountType, AssetClass, Holding, Security


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

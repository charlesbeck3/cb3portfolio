from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest

from portfolio.domain.analysis import PortfolioAnalysis
from portfolio.domain.portfolio import Portfolio as DomainPortfolio
from portfolio.models import Account, AssetClass, Holding

User = get_user_model()


@pytest.mark.domain
@pytest.mark.unit
def test_target_value_and_variance(test_portfolio: dict[str, Any]) -> None:
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]
    system = test_portfolio["system"]

    us_stocks = AssetClass.objects.create(name="US Stocks", category=system.cat_us_eq)
    bonds = AssetClass.objects.create(name="Bonds", category=system.cat_fi)

    acc_roth = Account.objects.create(
        user=user,
        name="Roth IRA",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )
    acc_taxable = Account.objects.create(
        user=user,
        name="Taxable",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    # Create new securities for this test to avoid conflicts
    from portfolio.models import Security

    sec_vti_test = Security.objects.create(ticker="VTI_TEST", asset_class=us_stocks)
    sec_bnd_test = Security.objects.create(ticker="BND_TEST", asset_class=bonds)

    Holding.objects.create(
        account=acc_roth,
        security=sec_vti_test,
        shares=Decimal("6"),
        current_price=Decimal("100"),
    )
    Holding.objects.create(
        account=acc_taxable,
        security=sec_bnd_test,
        shares=Decimal("4"),
        current_price=Decimal("100"),
    )

    domain_portfolio = DomainPortfolio(user_id=user.id, accounts=[acc_roth, acc_taxable])

    analysis = PortfolioAnalysis(
        portfolio=domain_portfolio,
        targets={
            "US Stocks": Decimal("50.00"),
            "Bonds": Decimal("50.00"),
        },
    )

    assert analysis.total_value == Decimal("1000")

    assert analysis.target_value_for("US Stocks") == Decimal("500")
    assert analysis.variance_for("US Stocks") == Decimal("100")
    assert analysis.variance_pct_for("US Stocks").quantize(Decimal("0.01")) == Decimal("10.00")

    assert analysis.target_value_for("Bonds") == Decimal("500")
    assert analysis.variance_for("Bonds") == Decimal("-100")
    assert analysis.variance_pct_for("Bonds").quantize(Decimal("0.01")) == Decimal("-10.00")


@pytest.mark.domain
@pytest.mark.unit
def test_variance_pct_for_zero_total(test_user: Any) -> None:
    empty = DomainPortfolio(user_id=test_user.id, accounts=[])
    analysis = PortfolioAnalysis(portfolio=empty, targets={"US Stocks": Decimal("50.00")})
    assert analysis.variance_pct_for("US Stocks") == Decimal("0.00")

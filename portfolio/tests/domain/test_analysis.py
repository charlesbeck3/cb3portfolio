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

    us_equities, _ = AssetClass.objects.get_or_create(  # type: ignore[attr-defined]
        name="US Equities", defaults={"category": system.cat_us_eq}
    )
    bonds = AssetClass.objects.create(name="Bonds", category=system.cat_fi)  # type: ignore[attr-defined]

    acc_roth = Account.objects.create(  # type: ignore[misc]
        user=user,
        name="Roth IRA",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )
    acc_taxable = Account.objects.create(  # type: ignore[misc]
        user=user,
        name="Taxable",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    # Create new securities for this test to avoid conflicts
    from portfolio.models import Security

    sec_vti_test = Security.objects.create(ticker="VTI_TEST", asset_class=us_equities)  # type: ignore[attr-defined]
    sec_bnd_test = Security.objects.create(ticker="BND_TEST", asset_class=bonds)  # type: ignore[attr-defined]

    Holding.objects.create(  # type: ignore[misc]
        account=acc_roth,
        security=sec_vti_test,
        shares=Decimal("6"),
    )
    Holding.objects.create(  # type: ignore[misc]
        account=acc_taxable,
        security=sec_bnd_test,
        shares=Decimal("4"),
    )

    # Create prices
    from django.utils import timezone

    from portfolio.models import SecurityPrice

    now = timezone.now()

    SecurityPrice.objects.create(
        security=sec_vti_test, price=Decimal("100"), price_datetime=now, source="manual"
    )
    SecurityPrice.objects.create(
        security=sec_bnd_test, price=Decimal("100"), price_datetime=now, source="manual"
    )

    domain_portfolio = DomainPortfolio(user_id=user.id, accounts=[acc_roth, acc_taxable])

    analysis = PortfolioAnalysis(
        portfolio=domain_portfolio,
        targets={
            "US Equities": Decimal("50.00"),
            "Bonds": Decimal("50.00"),
        },
    )

    assert analysis.total_value == Decimal("1000")

    assert analysis.target_value_for("US Equities") == Decimal("500")
    assert analysis.variance_for("US Equities") == Decimal("100")
    assert analysis.variance_pct_for("US Equities").quantize(Decimal("0.01")) == Decimal("10.00")

    assert analysis.target_value_for("Bonds") == Decimal("500")
    assert analysis.variance_for("Bonds") == Decimal("-100")
    assert analysis.variance_pct_for("Bonds").quantize(Decimal("0.01")) == Decimal("-10.00")


@pytest.mark.domain
@pytest.mark.unit
def test_variance_pct_for_zero_total(test_user: Any) -> None:
    empty = DomainPortfolio(user_id=test_user.id, accounts=[])
    analysis = PortfolioAnalysis(portfolio=empty, targets={"US Equities": Decimal("50.00")})
    assert analysis.variance_pct_for("US Equities") == Decimal("0.00")

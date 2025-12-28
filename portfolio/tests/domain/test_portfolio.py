"""
Tests for portfolio domain model (Aggregate Root).

Tests: portfolio/domain/portfolio.py
"""

from decimal import Decimal

from django.utils import timezone

import pytest

from portfolio.domain.portfolio import Portfolio
from portfolio.models import Account, Holding, SecurityPrice


@pytest.mark.domain
@pytest.mark.integration
class TestPortfolioDomain:
    """Tests for the pure logic of the Portfolio aggregate root."""

    @pytest.fixture
    def setup_data(self, test_user, base_system_data):
        system = base_system_data
        # Create a portfolio for the user
        from portfolio.models import Portfolio as PortfolioModel

        portfolio_model = PortfolioModel.objects.create(
            user=test_user, name="Domain Setup Portfolio"
        )

        acc_roth = Account.objects.create(
            user=test_user,
            name="Roth IRA",
            portfolio=portfolio_model,
            account_type=system.type_roth,
            institution=system.institution,
        )
        acc_taxable = Account.objects.create(
            user=test_user,
            name="Taxable",
            portfolio=portfolio_model,
            account_type=system.type_taxable,
            institution=system.institution,
        )

        # Create holdings
        Holding.objects.create(account=acc_roth, security=system.vti, shares=Decimal("6"))
        Holding.objects.create(account=acc_taxable, security=system.vxus, shares=Decimal("4"))

        # Create prices
        now = timezone.now()
        SecurityPrice.objects.create(
            security=system.vti, price=Decimal("100"), price_datetime=now, source="manual"
        )
        SecurityPrice.objects.create(
            security=system.vxus, price=Decimal("100"), price_datetime=now, source="manual"
        )

        return {
            "user": test_user,
            "accounts": [acc_roth, acc_taxable],
            "roth": acc_roth,
            "taxable": acc_taxable,
        }

    def test_len_and_iter(self, setup_data):
        """Verify portfolio iteration and length."""
        portfolio = Portfolio(user_id=setup_data["user"].id, accounts=setup_data["accounts"])
        assert len(portfolio) == 2
        assert [a.id for a in portfolio] == [a.id for a in setup_data["accounts"]]

    def test_total_value(self, setup_data):
        """Verify total value calculation across accounts."""
        portfolio = Portfolio(user_id=setup_data["user"].id, accounts=setup_data["accounts"])
        assert portfolio.total_value == Decimal("1000")

    def test_value_by_account_type(self, setup_data):
        """Verify aggregation by account type."""
        portfolio = Portfolio(user_id=setup_data["user"].id, accounts=setup_data["accounts"])
        by_type = portfolio.value_by_account_type()
        assert by_type["ROTH_IRA"] == Decimal("600")
        assert by_type["TAXABLE"] == Decimal("400")

    def test_value_by_asset_class(self, setup_data):
        """Verify aggregation by asset class."""
        portfolio = Portfolio(user_id=setup_data["user"].id, accounts=setup_data["accounts"])
        by_ac = portfolio.value_by_asset_class()
        # VTI is US Equities, VXUS is Intl Developed
        assert by_ac["US Equities"] == Decimal("600")
        assert by_ac["International Developed Equities"] == Decimal("400")

    def test_allocation_by_asset_class(self, setup_data):
        """Verify allocation percentage calculation."""
        portfolio = Portfolio(user_id=setup_data["user"].id, accounts=setup_data["accounts"])
        alloc = portfolio.allocation_by_asset_class()
        assert pytest.approx(alloc["US Equities"]) == 60.0
        assert pytest.approx(alloc["International Developed Equities"]) == 40.0

    def test_account_by_id(self, setup_data):
        """Verify finding account by ID."""
        portfolio = Portfolio(user_id=setup_data["user"].id, accounts=setup_data["accounts"])
        assert portfolio.account_by_id(setup_data["roth"].id) == setup_data["roth"]
        assert portfolio.account_by_id(999999) is None

    def test_accounts_by_type(self, setup_data):
        """Verify filtering accounts by type."""
        portfolio = Portfolio(user_id=setup_data["user"].id, accounts=setup_data["accounts"])
        assert portfolio.accounts_by_type("ROTH_IRA") == [setup_data["roth"]]
        assert portfolio.accounts_by_type("TAXABLE") == [setup_data["taxable"]]

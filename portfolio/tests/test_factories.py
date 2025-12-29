from django.contrib.auth import get_user_model

import pytest

from portfolio.models import (
    Account,
    AllocationStrategy,
    Holding,
    Portfolio,
    SecurityPrice,
    TargetAllocation,
)
from portfolio.tests import factories

User = get_user_model()


@pytest.mark.django_db
class TestFactories:
    def test_user_factory(self):
        user = factories.UserFactory()
        assert User.objects.count() == 1
        assert "user_" in user.username

    def test_portfolio_factory(self):
        portfolio = factories.PortfolioFactory()
        assert Portfolio.objects.count() == 1
        assert portfolio.user is not None

    def test_account_factory(self):
        account = factories.AccountFactory()
        assert Account.objects.count() == 1
        assert account.portfolio.user == account.user

    def test_holding_factory(self):
        holding = factories.HoldingFactory()
        assert Holding.objects.count() == 1
        assert holding.account is not None
        assert holding.security is not None

    def test_security_price_factory(self):
        price = factories.SecurityPriceFactory()
        assert SecurityPrice.objects.count() == 1
        assert price.security is not None

    def test_allocation_strategy_factory(self):
        factories.AllocationStrategyFactory()
        assert AllocationStrategy.objects.count() == 1

    def test_target_allocation_factory(self):
        target = factories.TargetAllocationFactory()
        assert TargetAllocation.objects.count() == 1
        assert target.strategy is not None
        assert target.asset_class is not None

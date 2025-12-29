"""Tests for custom Django managers."""

import pytest

from portfolio.models import Account, AllocationStrategy, Holding, TargetAllocation


@pytest.mark.integration
@pytest.mark.models
class TestAccountManager:
    """Test suite for AccountManager."""

    def test_for_user(self, test_user, base_system_data):
        """Test filtering accounts for specific user."""
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Main")

        # Account for test_user
        Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="My Account",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )
        # Account for other user calling the factory or just create user
        from users.models import CustomUser

        other = CustomUser.objects.create(email="other@example.com")
        other_portfolio = Portfolio.objects.create(user=other, name="Other")

        Account.objects.create(
            user=other,
            portfolio=other_portfolio,
            name="Other Account",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        qs = Account.objects.for_user(test_user)
        assert qs.count() == 1
        assert qs.first().name == "My Account"

    def test_get_summary_data(self, test_user, base_system_data):
        """Test get_summary_data prefetching."""
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Main")

        Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="My Account",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        # Should not raise
        qs = Account.objects.get_summary_data(test_user)
        assert qs.count() == 1
        # Access related fields to verify prefetch (though hard to verify prefetch strictly in test without django-debug-toolbar or checking queries)
        acc = qs.first()
        assert acc.institution.name == base_system_data.institution.name


@pytest.mark.integration
@pytest.mark.models
class TestHoldingManager:
    """Test suite for HoldingManager."""

    def test_for_user(self, test_user, base_system_data):
        """Test filtering holdings for specific user."""
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Main")

        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Acc",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )
        Holding.objects.create(account=account, security=base_system_data.vti, shares=10)

        qs = Holding.objects.for_user(test_user)
        assert qs.count() == 1

    def test_get_for_pricing(self, test_user, base_system_data):
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Main")

        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Acc",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )
        Holding.objects.create(account=account, security=base_system_data.vti, shares=10)

        qs = Holding.objects.get_for_pricing(test_user)
        assert qs.count() == 1
        # Access security
        assert qs.first().security.ticker == "VTI"

    def test_get_for_summary(self, test_user, base_system_data):
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Main")

        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Acc",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )
        Holding.objects.create(account=account, security=base_system_data.vti, shares=10)

        qs = Holding.objects.get_for_summary(test_user)
        assert qs.count() == 1

    def test_get_for_category_view(self, test_user, base_system_data):
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Main")

        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Acc",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )
        Holding.objects.create(account=account, security=base_system_data.vti, shares=10)

        qs = Holding.objects.get_for_category_view(test_user)
        assert qs.count() == 1


@pytest.mark.integration
@pytest.mark.models
class TestTargetAllocationManager:
    """Test suite for TargetAllocationManager."""

    def test_get_for_user(self, test_user, base_system_data):
        strategy = AllocationStrategy.objects.create(user=test_user, name="My Strat")
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=base_system_data.asset_class_us_equities,
            target_percent=100,
        )

        qs = TargetAllocation.objects.get_for_user(test_user)
        assert qs.count() == 1

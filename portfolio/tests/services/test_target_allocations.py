"""Tests for TargetAllocationViewService."""

from unittest.mock import Mock

import pytest

from portfolio.models import Account, AccountTypeStrategyAssignment, AllocationStrategy
from portfolio.services.target_allocations import TargetAllocationViewService


@pytest.mark.integration
@pytest.mark.services
class TestTargetAllocationViewService:
    """Test suite for TargetAllocationViewService."""

    def test_build_context_structure(self, test_user, base_system_data):
        """Test that build_context returns expected structure."""
        service = TargetAllocationViewService()
        context = service.build_context(user=test_user)

        assert "allocation_rows_percent" in context
        assert "allocation_rows_money" in context
        assert "strategies" in context
        assert "portfolio_total_value" in context

        # Verify strategies query
        assert list(context["strategies"]) == []

    def test_build_context_with_strategies(self, test_user):
        """Test that strategies are included in context."""
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        service = TargetAllocationViewService()
        context = service.build_context(user=test_user)

        assert strategy in context["strategies"]

    def test_save_from_post_requires_authentication(self):
        """Test that save_from_post requires authenticated user."""
        request = Mock()
        request.user.is_authenticated = False

        service = TargetAllocationViewService()
        success, messages = service.save_from_post(request=request)

        assert success is False
        assert "Authentication required." in messages

    def test_save_from_post_account_type_assignment(self, test_user, base_system_data):
        """Test saving account type strategy assignment."""
        from portfolio.models import Account, Portfolio

        # Create portfolio and account so the user is associated with the account type
        portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")
        Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Roth Account",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        # Mock request
        request = Mock()
        request.user = test_user
        # Simulate selecting a strategy for a specific account type
        request.POST = {f"strategy_at_{base_system_data.type_roth.id}": str(strategy.id)}

        service = TargetAllocationViewService()
        success, messages = service.save_from_post(request=request)

        assert success is True

        # Verify assignment created
        assignment = AccountTypeStrategyAssignment.objects.get(
            user=test_user, account_type=base_system_data.type_roth
        )
        assert assignment.allocation_strategy == strategy

    def test_save_from_post_remove_assignment(self, test_user, base_system_data):
        """Test removing an existing assignment."""
        from portfolio.models import Account, Portfolio

        # Create portfolio and account so the user is associated with the account type
        portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")
        Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Roth Account",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        # Create initial assignment
        AccountTypeStrategyAssignment.objects.create(
            user=test_user, account_type=base_system_data.type_roth, allocation_strategy=strategy
        )

        # Mock request with empty string for strategy (clearing it)
        request = Mock()
        request.user = test_user
        request.POST = {f"strategy_at_{base_system_data.type_roth.id}": ""}

        service = TargetAllocationViewService()
        success, messages = service.save_from_post(request=request)

        assert success is True
        assert not AccountTypeStrategyAssignment.objects.filter(
            user=test_user, account_type=base_system_data.type_roth
        ).exists()

    def test_save_from_post_account_override(self, test_user, base_system_data):
        """Test saving specific account strategy override."""
        from portfolio.models import Portfolio

        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")
        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Test Account",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
        )

        request = Mock()
        request.user = test_user
        request.POST = {f"strategy_acc_{account.id}": str(strategy.id)}

        service = TargetAllocationViewService()
        success, messages = service.save_from_post(request=request)

        assert success is True

        account.refresh_from_db()
        assert account.allocation_strategy == strategy

    def test_save_from_post_remove_account_override(self, test_user, base_system_data):
        """Test removing account strategy override."""
        from portfolio.models import Portfolio

        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")
        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Test Account",
            account_type=base_system_data.type_roth,
            institution=base_system_data.institution,
            allocation_strategy=strategy,
        )

        request = Mock()
        request.user = test_user
        request.POST = {f"strategy_acc_{account.id}": ""}

        service = TargetAllocationViewService()
        success, messages = service.save_from_post(request=request)

        assert success is True

        account.refresh_from_db()
        assert account.allocation_strategy is None

    def test_save_from_post_invalid_strategy(self, test_user, base_system_data):
        """Test robust handling of invalid strategy IDs."""
        request = Mock()
        request.user = test_user
        request.POST = {
            f"strategy_at_{base_system_data.type_roth.id}": "999999"  # Non-existent
        }

        service = TargetAllocationViewService()
        success, messages = service.save_from_post(request=request)

        # Should succeed but do nothing
        assert success is True
        assert not AccountTypeStrategyAssignment.objects.filter(
            user=test_user, account_type=base_system_data.type_roth
        ).exists()

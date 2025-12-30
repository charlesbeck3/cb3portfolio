"""Tests for security utilities."""

from django.contrib.auth import get_user_model
from django.http import Http404

import pytest

from portfolio.models import Account, AllocationStrategy, Holding, Portfolio
from portfolio.utils.security import (
    AccessControlError,
    InvalidInputError,
    sanitize_integer_input,
    validate_target_mode,
    validate_user_owns_account,
    validate_user_owns_holding,
    validate_user_owns_strategy,
    validate_view_mode,
)

User = get_user_model()


@pytest.mark.unit
class TestInputSanitization:
    """Test input sanitization functions."""

    def test_sanitize_integer_valid(self):
        """Test valid integer input."""
        assert sanitize_integer_input("123", "test_param") == 123
        assert sanitize_integer_input(456, "test_param") == 456

    def test_sanitize_integer_invalid(self):
        """Test invalid integer input."""
        with pytest.raises(InvalidInputError, match="must be a valid integer"):
            sanitize_integer_input("abc", "test_param")

        with pytest.raises(InvalidInputError, match="is required"):
            sanitize_integer_input(None, "test_param")

        with pytest.raises(InvalidInputError, match="must be a valid integer"):
            sanitize_integer_input("12.34", "test_param")

    def test_sanitize_integer_below_minimum(self):
        """Test integer below minimum value."""
        with pytest.raises(InvalidInputError, match="must be at least 1"):
            sanitize_integer_input(0, "test_param", min_val=1)

        with pytest.raises(InvalidInputError, match="must be at least 10"):
            sanitize_integer_input(5, "test_param", min_val=10)

    def test_validate_view_mode_valid(self):
        """Test valid view mode."""
        assert validate_view_mode("aggregated") == "aggregated"
        assert validate_view_mode("individual") == "individual"
        assert validate_view_mode("AGGREGATED") == "aggregated"  # Case insensitive
        assert validate_view_mode(None) == "aggregated"  # Default

    def test_validate_view_mode_invalid(self):
        """Test invalid view mode."""
        with pytest.raises(InvalidInputError, match="Invalid view mode"):
            validate_view_mode("invalid")

    def test_validate_target_mode_valid(self):
        """Test valid target mode."""
        assert validate_target_mode("effective") == "effective"
        assert validate_target_mode("policy") == "policy"
        assert validate_target_mode("POLICY") == "policy"  # Case insensitive
        assert validate_target_mode(None) == "effective"  # Default

    def test_validate_target_mode_invalid(self):
        """Test invalid target mode."""
        with pytest.raises(InvalidInputError, match="Invalid target mode"):
            validate_target_mode("invalid")


@pytest.mark.integration
class TestOwnershipValidation:
    """Test ownership validation functions."""

    @pytest.fixture
    def other_user(self, django_user_model):
        """Create a second user for ownership tests."""
        return django_user_model.objects.create_user(
            username="otheruser",
            password="testpass123",  # pragma: allowlist secret
        )

    def test_validate_user_owns_account_success(self, test_user, base_system_data):
        """Test successful account ownership validation."""
        portfolio = Portfolio.objects.create(user=test_user, name="Test")
        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Test Account",
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        result = validate_user_owns_account(test_user, account.id)
        assert result == account

    def test_validate_user_owns_account_wrong_user(self, test_user, other_user, base_system_data):
        """Test account ownership validation with wrong user."""
        portfolio = Portfolio.objects.create(user=other_user, name="Other")
        account = Account.objects.create(
            user=other_user,
            portfolio=portfolio,
            name="Other Account",
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )

        with pytest.raises(AccessControlError, match="do not have permission"):
            validate_user_owns_account(test_user, account.id)

    def test_validate_user_owns_account_not_found(self, test_user):
        """Test account ownership validation with non-existent account."""
        with pytest.raises(Http404, match="not found"):
            validate_user_owns_account(test_user, 99999)

    def test_validate_user_owns_holding_success(self, test_user, base_system_data):
        """Test successful holding ownership validation."""
        portfolio = Portfolio.objects.create(user=test_user, name="Test")
        account = Account.objects.create(
            user=test_user,
            portfolio=portfolio,
            name="Test Account",
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )
        holding = Holding.objects.create(account=account, security=base_system_data.vti, shares=100)

        result = validate_user_owns_holding(test_user, holding.id)
        assert result == holding

    def test_validate_user_owns_holding_wrong_user(self, test_user, other_user, base_system_data):
        """Test holding ownership validation with wrong user."""
        portfolio = Portfolio.objects.create(user=other_user, name="Other")
        account = Account.objects.create(
            user=other_user,
            portfolio=portfolio,
            name="Other Account",
            account_type=base_system_data.type_taxable,
            institution=base_system_data.institution,
        )
        holding = Holding.objects.create(account=account, security=base_system_data.vti, shares=100)

        with pytest.raises(AccessControlError, match="do not have permission"):
            validate_user_owns_holding(test_user, holding.id)

    def test_validate_user_owns_strategy_success(self, test_user):
        """Test successful strategy ownership validation."""
        strategy = AllocationStrategy.objects.create(user=test_user, name="Test Strategy")

        result = validate_user_owns_strategy(test_user, strategy.id)
        assert result == strategy

    def test_validate_user_owns_strategy_wrong_user(self, test_user, other_user):
        """Test strategy ownership validation with wrong user."""
        strategy = AllocationStrategy.objects.create(user=other_user, name="Other Strategy")

        with pytest.raises(AccessControlError, match="do not have permission"):
            validate_user_owns_strategy(test_user, strategy.id)

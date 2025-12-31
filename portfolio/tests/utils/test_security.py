"""Tests for security utilities."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.http import Http404

import pytest

from portfolio.models import Account, AllocationStrategy, Holding, Portfolio
from portfolio.utils.security import (
    AccessControlError,
    InvalidInputError,
    handle_holding_operation,
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


@pytest.mark.unit
class TestHandleHoldingOperation:
    """Test handle_holding_operation context manager."""

    @pytest.fixture
    def mock_request(self, rf, test_user):
        """Create mock request with user."""
        request = rf.post("/")
        request.user = test_user
        request._messages = Mock()
        return request

    @pytest.fixture
    def mock_account(self):
        """Create mock account."""
        account = Mock()
        account.id = 123
        return account

    def test_successful_operation_logs_completion(self, mock_request, mock_account, caplog):
        """Verify successful operation logs start and completion."""
        with patch("portfolio.utils.security.logger") as mock_logger:
            with handle_holding_operation(mock_request, mock_account, "test_operation"):
                pass  # Successful operation

            # Verify logging calls
            assert mock_logger.info.call_count == 2
            mock_logger.info.assert_any_call(
                "test_operation_started",
                operation="test_operation",
                user_id=mock_request.user.id,
                account_id=123,
            )
            mock_logger.info.assert_any_call(
                "test_operation_completed",
                operation="test_operation",
                user_id=mock_request.user.id,
                account_id=123,
            )

    def test_invalid_input_error_shows_message(self, mock_request, mock_account):
        """Verify InvalidInputError shows user message and logs warning."""
        with (
            patch("portfolio.utils.security.logger") as mock_logger,
            patch("portfolio.utils.security.messages") as mock_messages,
            handle_holding_operation(mock_request, mock_account, "test_operation"),
        ):
            raise InvalidInputError("Invalid shares value")

        # Verify error message shown to user
        mock_messages.error.assert_called_once_with(mock_request, "Invalid shares value")

        # Verify warning logged
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "test_operation_validation_failed"

    def test_access_control_error_shows_message(self, mock_request, mock_account):
        """Verify AccessControlError shows user message and logs warning."""
        with (
            patch("portfolio.utils.security.logger"),
            patch("portfolio.utils.security.messages") as mock_messages,
            handle_holding_operation(mock_request, mock_account, "test_operation"),
        ):
            raise AccessControlError("Account not owned by user")

        mock_messages.error.assert_called_once_with(mock_request, "Account not owned by user")

    def test_unexpected_error_logs_with_traceback(self, mock_request, mock_account):
        """Verify unexpected exceptions log with full traceback."""
        with (
            patch("portfolio.utils.security.logger") as mock_logger,
            patch("portfolio.utils.security.messages") as mock_messages,
            handle_holding_operation(mock_request, mock_account, "test_operation"),
        ):
            raise ValueError("Unexpected calculation error")

        # Generic message shown to user
        mock_messages.error.assert_called_once()
        assert "Error during test_operation" in str(mock_messages.error.call_args)

        # Full error logged with traceback
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args[1]
        assert call_kwargs["exc_info"] is True

    def test_additional_log_context_included(self, mock_request, mock_account):
        """Verify additional log context is included in logging."""
        with patch("portfolio.utils.security.logger") as mock_logger:
            with handle_holding_operation(
                mock_request,
                mock_account,
                "test_operation",
                log_context={"security_id": 456, "shares": "10.5"},
            ):
                pass

            # Check log context includes additional fields
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["security_id"] == 456
            assert call_kwargs["shares"] == "10.5"

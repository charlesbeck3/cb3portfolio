"""Security utilities for input validation and access control."""

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

import structlog

from portfolio.models import Account, AllocationStrategy, Holding

logger = structlog.get_logger(__name__)


class AccessControlError(PermissionDenied):
    """Raised when user attempts to access resources they don't own."""

    pass


class InvalidInputError(ValidationError):
    """Raised when input validation fails."""

    pass


def validate_user_owns_account(user: Any, account_id: int) -> Account:
    """
    Validate that user owns the specified account.

    Args:
        user: User object
        account_id: Account ID to validate

    Returns:
        Account object if validation passes

    Raises:
        Http404: If account doesn't exist
        AccessControlError: If account exists but user doesn't own it
    """
    try:
        account = Account.objects.select_related("portfolio", "account_type", "institution").get(
            id=account_id
        )
    except Account.DoesNotExist:
        logger.warning("account_not_found", user_id=user.id, account_id=account_id)
        raise Http404(f"Account with ID {account_id} not found") from None

    if account.user_id != user.id:
        logger.warning(
            "unauthorized_account_access_attempt",
            user_id=user.id,
            account_id=account_id,
            account_owner_id=account.user_id,
        )
        raise AccessControlError("You do not have permission to access this account")

    logger.debug("account_access_validated", user_id=user.id, account_id=account_id)

    return cast(Account, account)


def validate_user_owns_holding(user: Any, holding_id: int) -> Holding:
    """
    Validate that user owns the account containing the specified holding.

    Args:
        user: User object
        holding_id: Holding ID to validate

    Returns:
        Holding object if validation passes

    Raises:
        Http404: If holding doesn't exist
        AccessControlError: If holding exists but user doesn't own the account
    """
    try:
        holding = Holding.objects.select_related("account", "account__user", "security").get(
            id=holding_id
        )
    except Holding.DoesNotExist:
        logger.warning("holding_not_found", user_id=user.id, holding_id=holding_id)
        raise Http404(f"Holding with ID {holding_id} not found") from None

    if holding.account.user_id != user.id:
        logger.warning(
            "unauthorized_holding_access_attempt",
            user_id=user.id,
            holding_id=holding_id,
            account_owner_id=holding.account.user_id,
        )
        raise AccessControlError("You do not have permission to access this holding")

    logger.debug("holding_access_validated", user_id=user.id, holding_id=holding_id)

    return cast(Holding, holding)


def validate_user_owns_strategy(user: Any, strategy_id: int) -> AllocationStrategy:
    """
    Validate that user owns the specified allocation strategy.

    Args:
        user: User object
        strategy_id: Strategy ID to validate

    Returns:
        AllocationStrategy object if validation passes

    Raises:
        Http404: If strategy doesn't exist
        AccessControlError: If strategy exists but user doesn't own it
    """
    try:
        strategy = AllocationStrategy.objects.prefetch_related(
            "target_allocations__asset_class"
        ).get(id=strategy_id)
    except AllocationStrategy.DoesNotExist:
        logger.warning("strategy_not_found", user_id=user.id, strategy_id=strategy_id)
        raise Http404(f"Strategy with ID {strategy_id} not found") from None

    if strategy.user_id != user.id:
        logger.warning(
            "unauthorized_strategy_access_attempt",
            user_id=user.id,
            strategy_id=strategy_id,
            strategy_owner_id=strategy.user_id,
        )
        raise AccessControlError("You do not have permission to access this strategy")

    logger.debug("strategy_access_validated", user_id=user.id, strategy_id=strategy_id)

    return strategy


def validate_view_mode(view_mode: str | None) -> str:
    """
    Validate view mode parameter.

    Args:
        view_mode: View mode string from query params

    Returns:
        Validated view mode ('aggregated' or 'individual')

    Raises:
        InvalidInputError: If view mode is invalid
    """
    valid_modes = {"aggregated", "individual"}

    if view_mode is None:
        return "aggregated"  # Default

    mode = view_mode.lower()

    if mode not in valid_modes:
        logger.warning("invalid_view_mode", view_mode=view_mode, valid_modes=list(valid_modes))
        raise InvalidInputError(
            f"Invalid view mode: {view_mode}. Must be one of: {', '.join(valid_modes)}"
        )

    return mode


def validate_target_mode(target_mode: str | None) -> str:
    """
    Validate target mode parameter.

    Args:
        target_mode: Target mode string from query params

    Returns:
        Validated target mode ('effective' or 'policy')

    Raises:
        InvalidInputError: If target mode is invalid
    """
    valid_modes = {"effective", "policy"}

    if target_mode is None:
        return "effective"  # Default

    mode = target_mode.lower()

    if mode not in valid_modes:
        logger.warning(
            "invalid_target_mode", target_mode=target_mode, valid_modes=list(valid_modes)
        )
        raise InvalidInputError(
            f"Invalid target mode: {target_mode}. Must be one of: {', '.join(valid_modes)}"
        )

    return mode


def sanitize_integer_input(value: str | int | None, param_name: str, min_val: int = 1) -> int:
    """
    Sanitize and validate integer input.

    Args:
        value: Input value to sanitize
        param_name: Name of parameter (for error messages)
        min_val: Minimum allowed value

    Returns:
        Validated integer

    Raises:
        InvalidInputError: If value is invalid
    """
    if value is None:
        raise InvalidInputError(f"{param_name} is required")

    try:
        int_val = int(value)
    except (ValueError, TypeError) as e:
        logger.warning("invalid_integer_input", param_name=param_name, value=value, error=str(e))
        raise InvalidInputError(f"{param_name} must be a valid integer, got: {value}") from None

    if int_val < min_val:
        logger.warning(
            "integer_below_minimum", param_name=param_name, value=int_val, min_val=min_val
        )
        raise InvalidInputError(f"{param_name} must be at least {min_val}, got: {int_val}")

    return int_val

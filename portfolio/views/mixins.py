import logging
from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

import structlog

from portfolio.models import Account
from portfolio.utils.security import (
    AccessControlError,
    InvalidInputError,
    sanitize_integer_input,
    validate_user_owns_account,
)

logger = structlog.get_logger(__name__)
validation_logger = logging.getLogger(__name__)


class PortfolioContextMixin:
    """Provides common portfolio context data for portfolio views."""

    request: HttpRequest

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Insert sidebar data into context."""
        context = super().get_context_data(**kwargs)  # type: ignore
        context.update(self.get_sidebar_context())
        return context

    def get_sidebar_context(self) -> dict[str, Any]:
        """
        Get sidebar data for all portfolio views.

        REFACTORED: Now uses AllocationCalculationEngine.get_sidebar_data()
        for optimized data retrieval with minimal queries.

        Automatically updates prices from market data on each request.

        Returns:
            dict with 'sidebar_data' containing grand_total and groups
        """
        user = self.request.user
        if not user.is_authenticated:
            return {"sidebar_data": {"grand_total": Decimal("0.00"), "groups": {}}}

        from portfolio.services.allocations import get_sidebar_data
        from portfolio.services.pricing import PricingService

        # Auto-update prices on each page load if they are stale (>5 mins)
        pricing_service = PricingService()
        try:
            result = pricing_service.update_holdings_prices_if_stale(user)

            # Log results for monitoring
            if result["updated_count"] > 0:
                logger.info(
                    "prices_refreshed",
                    user_id=user.id,
                    updated=result["updated_count"],
                    skipped=result["skipped_count"],
                )

            if result["errors"]:
                logger.warning(
                    "price_update_errors", user_id=user.id, failed_tickers=result["errors"]
                )
        except Exception as e:
            # Log error but don't break the page if price fetch fails
            logger.error("price_service_error", user_id=user.id, error=str(e))

        # OPTIMIZED: Single consolidated call for all sidebar data
        sidebar_data = get_sidebar_data(user)

        # Log query count for monitoring (helps identify regressions)
        if sidebar_data["query_count"] > 10:
            logger.warning(
                "high_sidebar_query_count", user_id=user.id, queries=sidebar_data["query_count"]
            )

        # Format for template
        return {
            "sidebar_data": {
                "grand_total": sidebar_data["grand_total"],
                "groups": sidebar_data["accounts_by_group"],
            }
        }


class AccountOwnershipMixin:
    """
    Mixin that validates account ownership for account-scoped views.

    Provides consistent security validation across views that operate on
    a specific account (e.g., holdings, rebalancing, exports).

    Usage:
        class MyAccountView(LoginRequiredMixin, AccountOwnershipMixin, TemplateView):
            redirect_url = "portfolio:holdings"  # Optional, defaults to "portfolio:holdings"

            def get(self, request, *args, **kwargs):
                if not self.validate_account_ownership():
                    return redirect(self.redirect_url)
                return super().get(request, *args, **kwargs)

    Attributes:
        account: The validated Account instance (set after successful validation)
        redirect_url: URL name to redirect to on validation failure
    """

    request: HttpRequest
    kwargs: dict[str, Any]
    account: Account | None = None
    redirect_url: str = "portfolio:holdings"

    def validate_account_ownership(self) -> bool:
        """
        Validate that the current user owns the requested account.

        Extracts account_id from URL kwargs, validates the input, and verifies
        ownership. On success, sets self.account to the Account instance.

        Returns:
            True if validation passes, False otherwise (with error message added)
        """
        user = self.request.user
        account_id_raw = self.kwargs.get("account_id")

        try:
            account_id = sanitize_integer_input(account_id_raw, "account_id", min_val=1)
            self.account = validate_user_owns_account(user, account_id)
            return True

        except (InvalidInputError, AccessControlError) as e:
            validation_logger.warning(
                "Account validation failed: user=%s, account_id=%s, error=%s",
                user.id,
                account_id_raw,
                str(e),
            )
            messages.error(self.request, str(e))
            return False

    def get_validated_account(self) -> Account:
        """
        Get the validated account, raising an error if not validated.

        Call this after validate_account_ownership() has returned True.

        Returns:
            The validated Account instance

        Raises:
            ValueError: If called before successful validation
        """
        if self.account is None:
            raise ValueError("Account not validated. Call validate_account_ownership() first.")
        return self.account

    def get_redirect_response(self) -> HttpResponse:
        """
        Get the redirect response for failed validation.

        Returns:
            HttpResponseRedirect to self.redirect_url
        """
        return redirect(self.redirect_url)

import logging
from decimal import Decimal, DecimalException
from itertools import groupby
from operator import itemgetter
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from portfolio.models import Account, Holding, Security
from portfolio.services.allocations import AllocationEngine
from portfolio.utils.security import (
    AccessControlError,
    InvalidInputError,
    handle_holding_operation,
    sanitize_integer_input,
    validate_target_mode,
    validate_user_owns_account,
    validate_user_owns_holding,
    validate_view_mode,
)
from portfolio.views.mixins import PortfolioContextMixin

logger = logging.getLogger(__name__)


class HoldingsView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    """View for displaying and managing holdings."""

    template_name = "portfolio/holdings.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Handle GET requests with validation."""
        user = request.user

        # SECURITY: Validate account_id if provided
        account_id_raw = kwargs.get("account_id")
        if account_id_raw is not None:
            try:
                # Sanitize and validate integer input
                account_id = sanitize_integer_input(account_id_raw, "account_id", min_val=1)
                # Verify user owns this account
                validate_user_owns_account(user, account_id)
            except (InvalidInputError, AccessControlError) as e:
                logger.warning(
                    "Account validation failed: user=%s, account_id=%s, error=%s",
                    user.id,
                    account_id_raw,
                    str(e),
                )
                messages.error(request, str(e))
                return redirect("portfolio:holdings")
            except Http404:
                # Let 404 bubble up for non-existent IDs
                raise

        # SECURITY: Validate query parameters
        try:
            validate_view_mode(request.GET.get("view"))
            validate_target_mode(request.GET.get("target"))
        except InvalidInputError as e:
            logger.warning("Invalid query parameter: user=%s, error=%s", user.id, str(e))
            messages.warning(request, str(e))
            # Parameters will be defaulted in get_context_data

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Get context data with safe, validated inputs."""
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Initialize engine
        engine = AllocationEngine()

        # Get and sanitize inputs (re-validation is cheap or we just use defaults)
        account_id_raw = kwargs.get("account_id")

        try:
            validate_view_mode(self.request.GET.get("view"))
            target_mode = validate_target_mode(self.request.GET.get("target"))
        except InvalidInputError:
            # Fallback to safe defaults if validation failed in get()
            # view_mode = "aggregated" if not account_id_raw else "individual"
            target_mode = "effective"

        context["target_mode"] = target_mode

        # If account_id is provided, we already validated it in get()
        if account_id_raw:
            account_id = int(account_id_raw)
            context["account"] = Account.objects.get(id=account_id)
            context["securities"] = Security.objects.all().order_by("ticker")

        # Fetch holdings data
        # Default to aggregated unless account is specified
        if account_id_raw:
            context["holdings_rows"] = engine.get_holdings_rows(
                user=user, account_id=kwargs.get("account_id")
            )
            context["is_aggregated"] = False
        else:
            context["holdings_rows"] = engine.get_aggregated_holdings_rows(
                user=user, target_mode=target_mode
            )
            context["is_aggregated"] = True

        # Add sidebar context
        context.update(self.get_sidebar_context())

        return context

    def post(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        """Handle POST requests for adding/editing/deleting holdings."""
        user = request.user

        # SECURITY: Validate account_id
        account_id_raw = kwargs.get("account_id")
        if not account_id_raw:
            messages.error(request, "Can only edit holdings for a specific account.")
            return redirect("portfolio:holdings")

        try:
            account_id = sanitize_integer_input(account_id_raw, "account_id", min_val=1)
            account = validate_user_owns_account(user, account_id)
        except (InvalidInputError, AccessControlError) as e:
            messages.error(request, str(e))
            return redirect("portfolio:holdings")

        # Route to appropriate handler
        if "security_id" in request.POST:
            return self._handle_add_holding(request, account)
        elif "holding_ids" in request.POST:
            return self._handle_bulk_update(request, account)
        elif "delete_holding_id" in request.POST:
            return self._handle_delete_holding(request, account)

        messages.error(request, "Invalid form submission.")
        return redirect("portfolio:account_holdings", account_id=account.id)

    def _handle_add_holding(self, request: HttpRequest, account: Account) -> HttpResponse:
        """Handle adding a new holding with validation."""
        with handle_holding_operation(
            request,
            account,
            "add_holding",
            log_context={"form_action": "add"},
        ):
            # SECURITY: Validate security_id
            security_id = sanitize_integer_input(
                request.POST.get("security_id"), "security_id", min_val=1
            )

            try:
                security = Security.objects.get(id=security_id)
            except Security.DoesNotExist:
                raise InvalidInputError(f"Security with ID {security_id} not found") from None

            # Validate shares input
            shares_str = request.POST.get("shares", "").strip()
            if not shares_str:
                raise InvalidInputError("Shares is required")

            try:
                shares = Decimal(shares_str)
            except (ValueError, TypeError, DecimalException):
                raise InvalidInputError(
                    f"Shares must be a valid number, got: {shares_str}"
                ) from None

            if shares <= 0:
                raise InvalidInputError("Shares must be greater than zero")

            # Create holding
            holding, created = Holding.objects.get_or_create(
                account=account, security=security, defaults={"shares": shares}
            )

            if not created:
                messages.warning(
                    request,
                    f"Holding for {security.ticker} already exists. Please edit shares instead.",
                )
            else:
                messages.success(
                    request,
                    f"Added {shares.normalize():f} shares of {security.ticker} to {account.name}",
                )

        return redirect("portfolio:account_holdings", account_id=account.id)

    def _update_single_holding(
        self,
        request: HttpRequest,
        account: Account,
        holding_id_raw: str,
    ) -> bool:
        """
        Update a single holding's shares.

        Args:
            request: HTTP request
            account: Account containing the holding
            holding_id_raw: Raw holding ID from POST data

        Returns:
            True if holding was updated, False if skipped

        Raises:
            InvalidInputError: For validation failures
            AccessControlError: For permission failures
        """
        holding_id = sanitize_integer_input(holding_id_raw, "holding_id", min_val=1)
        shares_str = request.POST.get(f"shares_{holding_id}", "").strip()

        if not shares_str:
            return False  # Skip empty entries

        shares = Decimal(shares_str)
        if shares <= 0:
            return False  # Skip invalid shares

        # SECURITY: Validate ownership
        holding = validate_user_owns_holding(request.user, holding_id)

        # Cross-check: Ensure holding belongs to the account from URL
        if holding.account_id != account.id:
            logger.warning(
                "Account mismatch in bulk update: holding=%s, expected_account=%s, actual_account=%s",
                holding_id,
                account.id,
                holding.account_id,
            )
            return False

        # Only update if changed
        if holding.shares != shares:
            holding.shares = shares
            holding.save(update_fields=["shares"])
            return True

        return False

    def _handle_bulk_update(self, request: HttpRequest, account: Account) -> HttpResponse:
        """Handle bulk update of holdings with security validation."""
        with handle_holding_operation(
            request,
            account,
            "bulk_update_holdings",
            log_context={"form_action": "bulk_update"},
        ):
            updates_count = 0
            holding_ids = request.POST.getlist("holding_ids")

            for holding_id_raw in holding_ids:
                try:
                    if self._update_single_holding(request, account, holding_id_raw):
                        updates_count += 1
                except (
                    InvalidInputError,
                    AccessControlError,
                    ValueError,
                    TypeError,
                    DecimalException,
                ) as e:
                    # Log but continue processing other holdings
                    logger.warning(
                        "Skipping holding update due to validation error: id=%s, error=%s",
                        holding_id_raw,
                        str(e),
                    )
                    continue

            # Show appropriate message based on results
            if updates_count > 0:
                messages.success(request, f"Updated {updates_count} holdings.")
            else:
                messages.info(request, "No changes saved.")

        return redirect("portfolio:account_holdings", account_id=account.id)

    def _handle_delete_holding(self, request: HttpRequest, account: Account) -> HttpResponse:
        """Handle deleting a holding with validation."""
        with handle_holding_operation(
            request,
            account,
            "delete_holding",
            log_context={"form_action": "delete"},
        ):
            # SECURITY: Validate holding_id and ownership
            holding_id_raw = request.POST.get("delete_holding_id")
            holding_id = sanitize_integer_input(holding_id_raw, "holding_id", min_val=1)

            holding = validate_user_owns_holding(request.user, holding_id)

            # Verify holding belongs to this account
            if holding.account_id != account.id:
                raise AccessControlError("This holding does not belong to the specified account")

            # Delete holding
            security_ticker = holding.security.ticker
            shares_str = f"{holding.shares.normalize():f}"
            holding.delete()

            messages.success(
                request,
                f"Deleted {shares_str} shares of {security_ticker}",
            )

        return redirect("portfolio:account_holdings", account_id=account.id)


class TickerAccountDetailsView(LoginRequiredMixin, View):
    """Return HTML fragment with account-level holdings for a specific ticker."""

    def get(self, request: HttpRequest, ticker: str) -> HttpResponse:
        # Get all accounts for the user
        accounts = Account.objects.filter(user=request.user).select_related("account_type")

        # Get holdings for this ticker across all accounts
        holdings_data = []
        total_value = Decimal("0")
        total_shares = Decimal("0")

        for account in accounts:
            # We want the holding for this specific ticker
            account_holding = account.holdings.filter(security__ticker=ticker).first()

            if account_holding:
                value = account_holding.market_value
                shares = account_holding.shares

                total_value += value
                total_shares += shares

                account_total = account.total_value()
                pct_of_account = (
                    (value / account_total * 100) if account_total > 0 else Decimal("0")
                )

                holdings_data.append(
                    {
                        "account_name": account.name,
                        "account_type": account.account_type.label,
                        "account_type_id": account.account_type.id,
                        "shares": shares,
                        "value": value,
                        "pct_of_account": pct_of_account,
                        "pct_of_position": Decimal("0"),  # Calculate after we have total
                    }
                )

        # Recalculate pct_of_position now that we have total_value
        for h in holdings_data:
            h["pct_of_position"] = (
                (h["value"] / total_value * 100) if total_value > 0 else Decimal("0")
            )

        # Group by account type
        holdings_data.sort(key=itemgetter("account_type_id"))
        grouped = []

        for account_type, group in groupby(holdings_data, key=itemgetter("account_type")):
            group_list = list(group)
            group_total_value = sum(h["value"] for h in group_list)
            group_total_shares = sum(h["shares"] for h in group_list)
            group_pct_of_position = sum(h["pct_of_position"] for h in group_list)

            grouped.append(
                {
                    "account_type": account_type,
                    "subtotal": {
                        "shares": group_total_shares,
                        "value": group_total_value,
                        "pct_of_position": group_pct_of_position,
                    },
                    "holdings": group_list,
                }
            )

        context = {
            "ticker": ticker,
            "total_shares": total_shares,
            "total_value": total_value,
            "grouped_holdings": grouped,
        }

        return render(request, "portfolio/partials/ticker_details.html", context)

import contextlib
import logging
from decimal import Decimal
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from portfolio.models import Account, Holding, Security
from portfolio.views.mixins import PortfolioContextMixin

logger = logging.getLogger(__name__)


class HoldingsView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/holdings.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        logger.info(f"Holdings accessed by user {cast(Any, self.request.user).id}")
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated:
            return context

        account_id = kwargs.get("account_id")

        # Initialize engine and formatter (CONSISTENT WITH DASHBOARD/TARGETS)
        from portfolio.services.allocation_calculations import AllocationCalculationEngine
        from portfolio.services.allocation_presentation import AllocationPresentationFormatter

        engine = AllocationCalculationEngine()
        formatter = AllocationPresentationFormatter()

        # Step 1: Build numeric DataFrame with targets
        holdings_df = engine.calculate_holdings_with_targets(user, account_id)

        if holdings_df.empty:
            context["holdings_rows"] = []
        else:
            # Step 2: Format for display
            context["holdings_rows"] = formatter.format_holdings_rows(holdings_df)

        # Add sidebar context (same as before)
        context.update(self.get_sidebar_context())

        # Account-specific context (same as before)
        if account_id:
            with contextlib.suppress(Account.DoesNotExist):
                context["account"] = Account.objects.get(id=account_id, user=user)
                # Pass securities for the "Add Holding" modal
                context["securities"] = Security.objects.all().order_by("ticker")

        return context

    def post(self, request: Any, **kwargs: Any) -> Any:
        account_id = kwargs.get("account_id")
        if not account_id:
            messages.error(request, "Can only edit holdings for a specific account.")
            return redirect("portfolio:holdings")

        try:
            account = Account.objects.get(id=account_id, user=request.user)
        except Account.DoesNotExist:
            messages.error(request, "Account not found.")
            return redirect("portfolio:holdings")

        # 1. Handle Add Holding
        if "security_id" in request.POST:
            return self._handle_add_holding(request, account)

        # 2. Handle Delete Holding
        if "delete_ticker" in request.POST:
            return self._handle_delete_holding(request, account)

        # 3. Handle Bulk Update
        return self._handle_bulk_update(request, account)

    def _handle_add_holding(self, request: Any, account: Account) -> Any:
        from portfolio.forms.holdings import AddHoldingForm

        form = AddHoldingForm(request.POST)
        if form.is_valid():
            security_id = form.cleaned_data["security_id"]
            initial_shares = form.cleaned_data["initial_shares"]
            security = Security.objects.get(id=security_id)

            holding, created = Holding.objects.get_or_create(
                account=account, security=security, defaults={"shares": initial_shares}
            )

            if not created:
                messages.warning(
                    request,
                    f"Holding for {security.ticker} already exists. Please edit shares instead.",
                )
            else:
                messages.success(request, f"Added {security.ticker} to account.")
        else:
            for field, error_list in form.errors.items():
                for error in error_list:
                    messages.error(request, f"{field}: {error}")

        return redirect("portfolio:account_holdings", account_id=account.id)

    def _handle_delete_holding(self, request: Any, account: Account) -> Any:
        delete_ticker = request.POST.get("delete_ticker")
        if delete_ticker:
            delete_ticker = delete_ticker.strip().upper()
            try:
                holding_to_delete = Holding.objects.filter(
                    account=account, security__ticker=delete_ticker
                ).first()
                if holding_to_delete:
                    holding_to_delete.delete()
                    messages.success(request, f"Removed {delete_ticker} from account.")
                else:
                    messages.error(request, f"Holding {delete_ticker} not found.")
            except Exception as e:
                messages.error(request, f"Error deleting holding: {e}")

        return redirect("portfolio:account_holdings", account_id=account.id)

    def _handle_bulk_update(self, request: Any, account: Account) -> Any:
        updates_count = 0
        for key, value in request.POST.items():
            if not value:
                continue

            if key.startswith("shares_"):
                ticker = key.replace("shares_", "")
                try:
                    shares = Decimal(value)
                    target_holding = Holding.objects.filter(
                        account=account, security__ticker=ticker
                    ).first()
                    if target_holding:
                        target_holding.shares = shares
                        target_holding.save()
                        updates_count += 1
                except (ValueError, IndexError):
                    pass

        if updates_count > 0:
            messages.success(request, f"Updated {updates_count} holdings.")
        else:
            messages.info(request, "No changes saved.")

        return redirect("portfolio:account_holdings", account_id=account.id)

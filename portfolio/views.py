import contextlib
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from portfolio.models import Account
from portfolio.services import PortfolioSummaryService


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/index.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Get summary data
        context['summary'] = PortfolioSummaryService.get_holdings_summary(self.request.user)
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(self.request.user)

        # Pass account types for column headers
        # Only include account types that have at least one account
        assert self.request.user.is_authenticated
        existing_types = set(
            Account.objects.filter(user=self.request.user)
            .values_list('account_type', flat=True)
            .distinct()
        )
        context['account_types'] = [
            (code, label) for code, label in Account.ACCOUNT_TYPES
            if code in existing_types
        ]

        return context


class HoldingsView(LoginRequiredMixin, TemplateView):
    template_name = 'portfolio/holdings.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        account_id = kwargs.get('account_id')

        context.update(PortfolioSummaryService.get_holdings_by_category(self.request.user, account_id))
        context['sidebar_data'] = PortfolioSummaryService.get_account_summary(self.request.user)

        if account_id and self.request.user.is_authenticated:
                 with contextlib.suppress(Account.DoesNotExist):
                     context['account'] = Account.objects.get(id=account_id, user=self.request.user)

        return context

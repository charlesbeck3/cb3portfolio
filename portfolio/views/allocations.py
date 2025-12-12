from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from portfolio.views.mixins import PortfolioContextMixin


class AllocationsView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/allocations.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        user = self.request.user
        assert user.is_authenticated

        # Allocations view currently only needs sidebar data; delegate to mixin.
        context.update(self.get_sidebar_context(user))
        return context

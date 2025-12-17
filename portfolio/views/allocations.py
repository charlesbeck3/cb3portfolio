from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from portfolio.views.mixins import PortfolioContextMixin


class AllocationsView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    """Display allocations page with sidebar context."""

    template_name = "portfolio/allocations.html"

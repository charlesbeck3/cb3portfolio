from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView

from portfolio.forms.strategies import AllocationStrategyForm
from portfolio.models import AllocationStrategy, AssetClass, TargetAllocation
from portfolio.views.mixins import PortfolioContextMixin


class AllocationStrategyCreateView(LoginRequiredMixin, PortfolioContextMixin, CreateView):
    """View to create a new Allocation Strategy."""

    model = AllocationStrategy
    form_class = AllocationStrategyForm
    template_name = "portfolio/allocation_strategy_form.html"
    success_url = reverse_lazy("portfolio:target_allocations")

    def form_valid(self, form: Any) -> HttpResponseRedirect:
        with transaction.atomic():
            # 1. Save the Strategy itself
            form.instance.user = self.request.user
            self.object = form.save()

            # 2. Save Target Allocations
            asset_classes = AssetClass.objects.all()
            for ac in asset_classes:
                field_name = f"target_{ac.id}"
                raw_value = form.cleaned_data.get(field_name)

                # Only create records for non-zero allocations
                if raw_value and raw_value > 0:
                     TargetAllocation.objects.create(
                         strategy=self.object,
                         asset_class=ac,
                         target_percent=raw_value
                     )

        messages.success(self.request, f"Strategy '{self.object.name}' created successfully.")
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        # Add sidebar context
        context.update(self.get_sidebar_context())
        return context

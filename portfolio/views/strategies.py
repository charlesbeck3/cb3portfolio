from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from portfolio.forms.strategies import AllocationStrategyForm
from portfolio.models import AllocationStrategy, AssetClass
from portfolio.views.mixins import PortfolioContextMixin


class AllocationStrategyCreateView(LoginRequiredMixin, PortfolioContextMixin, CreateView):
    """View to create a new Allocation Strategy."""

    model = AllocationStrategy
    form_class = AllocationStrategyForm
    template_name = "portfolio/allocation_strategy_form.html"
    success_url = reverse_lazy("portfolio:target_allocations")

    def form_valid(self, form: Any) -> HttpResponseRedirect | Any:
        with transaction.atomic():
            # 1. Save the Strategy itself
            form.instance.user = cast(Any, self.request.user)
            self.object = form.save()

            # 2. Collect allocations from form (including optional cash)
            allocations = {}
            asset_classes = AssetClass.objects.all()

            for ac in asset_classes:
                field_name = f"target_{ac.id}"
                raw_value = form.cleaned_data.get(field_name)

                # Only include non-zero allocations
                if raw_value and raw_value > 0:
                    allocations[ac.id] = raw_value

            # 3. Save allocations (automatically calculates cash if not provided)
            try:
                self.object.save_allocations(allocations)
            except ValueError as e:
                form.add_error(None, str(e))
                return self.form_invalid(form)

        messages.success(
            self.request,
            f"Strategy '{self.object.name}' created successfully. Cash allocation: {self.object.cash_allocation}%",
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        # Add sidebar context
        context.update(self.get_sidebar_context())
        return context


class AllocationStrategyUpdateView(LoginRequiredMixin, PortfolioContextMixin, UpdateView):
    """View to edit an existing Allocation Strategy."""

    model = AllocationStrategy
    form_class = AllocationStrategyForm
    template_name = "portfolio/allocation_strategy_form.html"
    success_url = reverse_lazy("portfolio:target_allocations")

    def get_queryset(self) -> Any:
        """Ensure user can only edit their own strategies."""
        return AllocationStrategy.objects.filter(user=cast(Any, self.request.user))

    def form_valid(self, form: Any) -> HttpResponseRedirect | Any:
        with transaction.atomic():
            # Update the strategy
            self.object = form.save()

            # Collect allocations (including optional cash)
            allocations = {}
            asset_classes = AssetClass.objects.all()

            for ac in asset_classes:
                field_name = f"target_{ac.id}"
                raw_value = form.cleaned_data.get(field_name)

                if raw_value and raw_value > 0:
                    allocations[ac.id] = raw_value

            # Save allocations (automatically calculates cash if not provided)
            try:
                self.object.save_allocations(allocations)
            except ValueError as e:
                form.add_error(None, str(e))
                return self.form_invalid(form)

        messages.success(
            self.request,
            f"Strategy '{self.object.name}' updated successfully. Cash allocation: {self.object.cash_allocation}%",
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(self.get_sidebar_context())
        return context

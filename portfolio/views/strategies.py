from __future__ import annotations

import logging
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from portfolio.exceptions import AllocationError
from portfolio.forms.strategies import AllocationStrategyForm
from portfolio.models import AllocationStrategy, AssetClass
from portfolio.utils.security import (
    AccessControlError,
    InvalidInputError,
    sanitize_integer_input,
    validate_user_owns_strategy,
)
from portfolio.views.mixins import PortfolioContextMixin

logger = logging.getLogger(__name__)


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

            # 3. Pre-validate before attempting to save
            # This provides better error messages than catching ValueError
            # Check if cash was provided to determine if we allow implicit cash
            cash_ac = AssetClass.get_cash()
            cash_provided = cash_ac.id in allocations if cash_ac else False

            is_valid, error_msg = self.object.validate_allocations(
                allocations, allow_implicit_cash=not cash_provided
            )
            if not is_valid:
                form.add_error(None, error_msg)
                return self.form_invalid(form)

            # 4. Save allocations (automatically calculates cash if not provided)
            # This also has its own defensive validation as a last resort
            try:
                self.object.save_allocations(allocations)
            except (AllocationError, ValueError) as e:
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

    def get_object(self, queryset: Any = None) -> AllocationStrategy:
        """Get strategy object with ownership validation."""
        strategy_id_raw = self.kwargs.get("pk")

        try:
            # Sanitize input
            strategy_id = sanitize_integer_input(strategy_id_raw, "strategy_id", min_val=1)

            # Validate ownership
            strategy = validate_user_owns_strategy(self.request.user, strategy_id)

            return strategy

        except (InvalidInputError, AccessControlError) as e:
            logger.warning(
                "Invalid strategy access: user=%s, strategy_id=%s, error=%s",
                self.request.user.id,
                strategy_id_raw,
                str(e),
            )
            messages.error(self.request, str(e))
            raise Http404("Strategy not found") from None
        except Exception:
            logger.error(
                "Unexpected error accessing strategy: user=%s, strategy_id=%s",
                self.request.user.id,
                strategy_id_raw,
                exc_info=True,
            )
            raise Http404("Strategy not found") from None

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

            # 3. Pre-validate before attempting to save
            cash_ac = AssetClass.get_cash()
            cash_provided = cash_ac.id in allocations if cash_ac else False

            is_valid, error_msg = self.object.validate_allocations(
                allocations, allow_implicit_cash=not cash_provided
            )
            if not is_valid:
                form.add_error(None, error_msg)
                return self.form_invalid(form)

            # 4. Save allocations (automatically calculates cash if not provided)
            try:
                self.object.save_allocations(allocations)
            except (AllocationError, ValueError) as e:
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

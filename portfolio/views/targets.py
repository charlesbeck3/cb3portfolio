from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

import structlog

from portfolio.services.target_allocations import TargetAllocationViewService
from portfolio.views.mixins import PortfolioContextMixin

logger = structlog.get_logger(__name__)


class TargetAllocationView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = "portfolio/target_allocations.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = TargetAllocationViewService()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        logger.info("target_allocations_accessed", user_id=cast(Any, self.request.user).id)
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_authenticated:
            return context

        user = cast(Any, user)
        context.update(self._service.build_context(user=user))
        return context

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        ok, errors = self._service.save_from_post(request=request)
        if not ok:
            for err in errors:
                messages.error(request, err)
            return redirect("portfolio:target_allocations")

        messages.success(request, "Allocations updated.")
        return redirect("portfolio:target_allocations")

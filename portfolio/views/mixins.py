from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from portfolio.services import PortfolioSummaryService, TargetAllocationService

__all__ = ["PortfolioContextMixin"]


class PortfolioContextMixin:
    """Provides common portfolio context data for portfolio views."""

    request: HttpRequest

    _summary_service: PortfolioSummaryService | None = None

    @property
    def summary_service(self) -> PortfolioSummaryService:
        if self._summary_service is None:
            self._summary_service = PortfolioSummaryService()
        return self._summary_service

    def get_portfolio_services(self) -> dict[str, Any]:
        if not hasattr(self, "_services"):
            self._services = {
                "summary": PortfolioSummaryService(),
                "targets": TargetAllocationService(),
            }
        return self._services

    def get_sidebar_context(self) -> dict[str, Any]:
        """Get sidebar data for all portfolio views."""

        user = self.request.user
        assert user.is_authenticated
        return {"sidebar_data": self.summary_service.get_account_summary(user)}

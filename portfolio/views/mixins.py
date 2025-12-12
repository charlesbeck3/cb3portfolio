from __future__ import annotations

from typing import Any

from portfolio.services import PortfolioSummaryService, TargetAllocationService

__all__ = ["PortfolioContextMixin"]


class PortfolioContextMixin:
    """Provides common portfolio context data for portfolio views."""

    def get_portfolio_services(self) -> dict[str, Any]:
        if not hasattr(self, "_services"):
            self._services = {
                "summary": PortfolioSummaryService(),
                "targets": TargetAllocationService(),
            }
        return self._services

    def get_sidebar_context(self, user: Any) -> dict[str, Any]:
        """Get sidebar data for all portfolio views."""

        service = self.get_portfolio_services()["summary"]
        return {"sidebar_data": service.get_account_summary(user)}

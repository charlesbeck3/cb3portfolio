"""
Health check endpoint for monitoring and load balancers.

Provides application health status including database connectivity
and version information for debugging.
"""

from typing import Any

from django.db import connection
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

import structlog

logger = structlog.get_logger(__name__)


@method_decorator(never_cache, name="dispatch")
class HealthCheckView(View):
    """
    Comprehensive health check endpoint.

    Checks:
    - Application is running (implicit - returns 200)
    - Database connectivity
    - Django version

    Returns:
        200 OK: All checks passed
        503 Service Unavailable: Database check failed

    Response format:
        {
            "status": "healthy" | "unhealthy",
            "checks": {
                "database": "ok" | "error: <message>",
                "version": "1.0.0"
            }
        }
    """

    def get(self, request: Any) -> JsonResponse:
        """Return comprehensive health status."""
        checks: dict[str, str] = {}
        overall_status = "healthy"
        status_code = 200

        # Database connectivity check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
            logger.debug("health_check_database_ok")
        except Exception as e:
            checks["database"] = f"error: {str(e)}"
            overall_status = "unhealthy"
            status_code = 503
            logger.error("health_check_database_failed", error=str(e), exc_info=True)

        # Version information (for debugging)
        checks["version"] = "1.0.0"

        return JsonResponse(
            {
                "status": overall_status,
                "checks": checks,
            },
            status=status_code,
        )

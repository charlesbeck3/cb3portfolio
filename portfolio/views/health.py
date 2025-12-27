"""Health check endpoint for monitoring and load balancers."""

from django.http import JsonResponse
from django.views import View


class HealthCheckView(View):
    """
    Simple health check endpoint.

    Returns HTTP 200 with JSON status for monitoring systems.
    No authentication required - public endpoint.

    Usage:
        GET /health/ -> {"status": "healthy", "version": "1.0.0"}
    """

    def get(self, request):
        """Return health status."""
        return JsonResponse(
            {
                "status": "healthy",
                "version": "1.0.0",
            }
        )

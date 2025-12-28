"""
Performance timing middleware for identifying slow requests.

Logs warning for requests that exceed configured threshold.
"""

import time
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

import structlog

logger = structlog.get_logger(__name__)


class PerformanceTimingMiddleware:
    """
    Middleware that times request processing and logs slow requests.

    Logs a warning if request processing time exceeds the threshold
    defined in settings.SLOW_REQUEST_THRESHOLD (default: 1.0 seconds).

    The request duration is also added to response headers for debugging.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        # Threshold in seconds for what constitutes a "slow" request
        self.slow_threshold = getattr(settings, "SLOW_REQUEST_THRESHOLD", 1.0)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start_time = time.time()

        response = self.get_response(request)

        duration = time.time() - start_time

        # Add timing header to response
        response["X-Request-Duration"] = f"{duration:.3f}s"

        # Log slow requests
        if duration > self.slow_threshold:
            logger.warning(
                "slow_request_detected",
                duration=duration,
                path=request.path,
                method=request.method,
                threshold=self.slow_threshold,
            )

        return response

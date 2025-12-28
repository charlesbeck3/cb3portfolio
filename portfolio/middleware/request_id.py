"""
Request ID middleware for tracing requests through logs.

Adds a unique request ID to each request that can be used to correlate
log entries across the entire request lifecycle.
"""

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

import structlog


class RequestIDMiddleware:
    """
    Middleware that generates a unique request ID for each request.

    The request ID is:
    - Accepted from X-Request-ID header if present (for load balancer tracing)
    - Generated as new UUID if not present
    - Added to the request object as request.id
    - Added to the response headers as X-Request-ID
    - Added to structlog context for automatic inclusion in all logs

    This enables tracing a single request through all log entries.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Check if request already has an ID (e.g., from load balancer)
        request_id = request.headers.get("X-Request-ID")

        if not request_id:
            # Generate new UUID for this request
            request_id = str(uuid.uuid4())

        # Store on request object
        request.id = request_id  # type: ignore

        # Bind to structlog context for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = self.get_response(request)
        finally:
            # Clean up context after request completes
            structlog.contextvars.clear_contextvars()

        # Add request ID to response headers for debugging
        response["X-Request-ID"] = request_id

        return response

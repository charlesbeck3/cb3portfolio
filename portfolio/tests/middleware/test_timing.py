import time

from django.http import HttpResponse

import pytest

from portfolio.middleware.timing import PerformanceTimingMiddleware


@pytest.mark.unit
@pytest.mark.middleware
class TestPerformanceTimingMiddleware:
    """Test PerformanceTimingMiddleware adds timing headers."""

    def test_middleware_adds_timing_header(self, rf):
        """Test that middleware adds X-Request-Duration header."""

        def get_response(request):
            return HttpResponse("OK")

        middleware = PerformanceTimingMiddleware(get_response)
        request = rf.get("/test/")

        response = middleware(request)

        assert "X-Request-Duration" in response
        assert response["X-Request-Duration"].endswith("s")

    def test_middleware_timing_accuracy(self, rf):
        """Test that timing is reasonably accurate."""

        def slow_response(request):
            time.sleep(0.1)  # 100ms delay
            return HttpResponse("OK")

        middleware = PerformanceTimingMiddleware(slow_response)
        request = rf.get("/test/")

        response = middleware(request)

        # Parse timing from header (e.g., "0.100s")
        duration_str = response["X-Request-Duration"]
        duration_s = float(duration_str.replace("s", ""))

        # Should be at least 100ms
        assert duration_s >= 0.1

    def test_middleware_slow_request_logging(self, rf, monkeypatch):
        """Test that slow requests are logged."""

        # We need to capture logs. structlog is a bit tricky to mock,
        # but we can try to mock the logger.warning directly if we know where it's used.
        from portfolio.middleware import timing

        log_calls = []

        def mock_warning(event, **kwargs):
            log_calls.append((event, kwargs))

        monkeypatch.setattr(timing.logger, "warning", mock_warning)
        # Set threshold very low for testing
        monkeypatch.setattr(
            timing.PerformanceTimingMiddleware,
            "__init__",
            lambda self, get_response: setattr(self, "get_response", get_response)
            or setattr(self, "slow_threshold", 0.01),
        )

        def slow_response(request):
            time.sleep(0.02)
            return HttpResponse("OK")

        middleware = timing.PerformanceTimingMiddleware(slow_response)
        request = rf.get("/test-slow/")
        middleware(request)

        assert len(log_calls) == 1
        assert log_calls[0][0] == "slow_request_detected"
        assert log_calls[0][1]["path"] == "/test-slow/"
        assert log_calls[0][1]["duration"] >= 0.02

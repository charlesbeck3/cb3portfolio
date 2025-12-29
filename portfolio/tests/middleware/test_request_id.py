"""Tests for Request ID middleware."""

from django.http import HttpResponse
from django.test import RequestFactory

import pytest

from portfolio.middleware import RequestIDMiddleware


@pytest.mark.unit
@pytest.mark.middleware
class TestRequestIDMiddleware:
    """Test suite for RequestIDMiddleware."""

    def test_adds_request_id_to_request(self):
        """Test that middleware adds request_id attribute to request."""
        factory = RequestFactory()
        request = factory.get("/")

        def get_response(req):
            # Verify request_id was added (middleware uses .id)
            assert hasattr(req, "id")
            assert isinstance(req.id, str)
            assert len(req.id) > 0
            return HttpResponse()

        middleware = RequestIDMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 200

    def test_adds_request_id_header_to_response(self):
        """Test that middleware adds X-Request-ID header to response."""
        factory = RequestFactory()
        request = factory.get("/")

        def get_response(req):
            return HttpResponse()

        middleware = RequestIDMiddleware(get_response)
        response = middleware(request)

        assert "X-Request-ID" in response
        assert len(response["X-Request-ID"]) > 0

    def test_request_id_is_consistent(self):
        """Test that request_id on request matches header on response."""
        factory = RequestFactory()
        request = factory.get("/")

        captured_request_id = None

        def get_response(req):
            nonlocal captured_request_id
            captured_request_id = req.id
            return HttpResponse()

        middleware = RequestIDMiddleware(get_response)
        response = middleware(request)

        assert response["X-Request-ID"] == captured_request_id

    def test_request_id_is_unique_per_request(self):
        """Test that each request gets a unique request_id."""
        factory = RequestFactory()

        def get_response(req):
            return HttpResponse()

        middleware = RequestIDMiddleware(get_response)

        request1 = factory.get("/")
        response1 = middleware(request1)
        id1 = response1["X-Request-ID"]

        request2 = factory.get("/")
        response2 = middleware(request2)
        id2 = response2["X-Request-ID"]

        assert id1 != id2

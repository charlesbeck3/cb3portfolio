"""Tests for custom error pages."""

from django.test import override_settings

import pytest


@pytest.mark.views
@pytest.mark.integration
@override_settings(DEBUG=False)
def test_404_page_renders(client):
    """Test that 404 page renders with custom template."""
    response = client.get("/nonexistent-page/")
    assert response.status_code == 404
    assert b"Page Not Found" in response.content
    assert b"Return to Dashboard" in response.content


@pytest.mark.views
@pytest.mark.integration
@override_settings(DEBUG=False)
def test_404_page_has_dashboard_link(client):
    """Test that 404 page includes link back to dashboard."""
    response = client.get("/this-does-not-exist/")
    assert response.status_code == 404
    # Check for dashboard URL in response
    assert b'href="/"' in response.content or b"Return to Dashboard" in response.content

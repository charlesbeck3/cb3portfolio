"""Tests for health check endpoint."""

from django.urls import reverse

import pytest


@pytest.mark.views
@pytest.mark.integration
def test_health_check_returns_200(client):
    """Health check should return 200 OK."""
    url = reverse("health")
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.views
@pytest.mark.integration
def test_health_check_returns_json(client):
    """Health check should return JSON with status."""
    url = reverse("health")
    response = client.get(url)
    assert response["Content-Type"] == "application/json"

    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.views
@pytest.mark.integration
def test_health_check_no_auth_required(client):
    """Health check should work without authentication."""
    # No login needed
    url = reverse("health")
    response = client.get(url)
    assert response.status_code == 200

"""Tests for health check endpoint."""

from unittest.mock import patch

from django.db import OperationalError
from django.urls import reverse

import pytest


@pytest.mark.views
@pytest.mark.integration
@pytest.mark.django_db
def test_health_check_returns_200_when_healthy(client):
    """Health check should return 200 OK when all checks pass."""
    url = reverse("health")
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.views
@pytest.mark.integration
def test_health_check_returns_json(client):
    """Health check should return JSON with status and checks."""
    url = reverse("health")
    response = client.get(url)
    assert response["Content-Type"] == "application/json"

    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "version" in data["checks"]


@pytest.mark.views
@pytest.mark.integration
@pytest.mark.django_db
def test_health_check_healthy_status(client):
    """Health check should report healthy when database is accessible."""
    url = reverse("health")
    response = client.get(url)
    data = response.json()

    assert data["status"] == "healthy"
    assert data["checks"]["database"] == "ok"


@pytest.mark.views
@pytest.mark.integration
@pytest.mark.django_db
def test_health_check_no_auth_required(client):
    """Health check should work without authentication."""
    # No login needed
    url = reverse("health")
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.views
@pytest.mark.integration
def test_health_check_database_failure(client):
    """Health check should return 503 when database is unavailable."""
    url = reverse("health")

    # Mock database failure
    with patch("django.db.connection.cursor") as mock_cursor:
        mock_cursor.side_effect = OperationalError("Database connection failed")
        response = client.get(url)

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "error" in data["checks"]["database"]


@pytest.mark.views
@pytest.mark.integration
def test_health_check_not_cached(client):
    """Health check responses should not be cached."""
    url = reverse("health")
    response = client.get(url)

    # The @never_cache decorator should prevent caching
    cache_control = response.get("Cache-Control", "")
    assert cache_control != ""

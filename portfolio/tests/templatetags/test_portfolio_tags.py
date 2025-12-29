"""
Tests for portfolio template tags.

Tests: portfolio/templatetags/portfolio_tags.py
"""

import pytest

from portfolio.templatetags.portfolio_tags import variance_class


@pytest.mark.templatetags
@pytest.mark.unit
class TestPortfolioTags:
    """Tests for individual portfolio template filters."""

    def test_variance_class_filter(self) -> None:
        """Test variance CSS class generation."""
        assert variance_class(6) == "text-danger"
        assert variance_class(-6) == "text-danger"
        assert variance_class(4) == "text-success"
        assert variance_class(-4) == "text-success"
        assert variance_class(5) == "text-success"  # Default threshold 5 (inclusive as success)
        assert variance_class(5.1) == "text-danger"

        # Test custom threshold
        assert variance_class(2, threshold=1) == "text-danger"
        assert variance_class("invalid") == ""

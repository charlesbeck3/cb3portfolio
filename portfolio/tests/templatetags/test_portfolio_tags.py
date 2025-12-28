"""
Tests for portfolio template tags.

Tests: portfolio/templatetags/portfolio_tags.py
"""

import pytest

from portfolio.templatetags.portfolio_tags import currency, percentage, variance_class


@pytest.mark.templatetags
@pytest.mark.unit
class TestPortfolioTags:
    """Tests for individual portfolio template filters."""

    def test_currency_filter(self) -> None:
        """Test currency formatting."""
        assert currency(1234.56) == "$1,234.56"
        assert currency("1234.56") == "$1,234.56"
        assert currency(1234) == "$1,234.00"
        assert currency(0) == "$0.00"
        assert currency("invalid") == "invalid"

    def test_percentage_filter(self) -> None:
        """Test percentage formatting."""
        assert percentage(12.3456) == "12.35%"
        assert percentage(12.3456, 1) == "12.3%"
        assert percentage("12.34") == "12.34%"
        assert percentage(0) == "0.00%"
        assert percentage("invalid") == "invalid"

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

"""
Tests for allocation template tags.

Tests: portfolio/templatetags/allocation_tags.py
"""

from decimal import Decimal

import pytest

from portfolio.templatetags.allocation_tags import (
    row_css_class,
    variance_css_class,
)


@pytest.mark.templatetags
@pytest.mark.unit
class TestAllocationTags:
    """Tests for allocation-specific template filters."""

    def test_row_css_class(self) -> None:
        """Verify CSS classes for different row types."""
        assert row_css_class("asset") == ""
        assert row_css_class("subtotal") == "subtotal"
        assert row_css_class("group_total") == "group-total"
        assert row_css_class("grand_total") == "grand-total"
        assert row_css_class("unknown") == ""

    def test_variance_css_class_numeric(self) -> None:
        """Verify variance coloring for numeric inputs."""
        assert variance_css_class(5.0) == "variance-positive"
        assert variance_css_class(-5.0) == "variance-negative"
        assert variance_css_class(Decimal("1.5")) == "variance-positive"
        assert variance_css_class(0) == ""

    def test_variance_css_class_string(self) -> None:
        """Verify variance coloring for formatted string inputs."""
        assert variance_css_class("+5.2%") == "variance-positive"
        assert variance_css_class("-3.1%") == "variance-negative"
        assert variance_css_class("($1,000)") == "variance-negative"
        assert variance_css_class("$500") == "variance-positive"
        assert variance_css_class("invalid") == ""

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
        # Standard types
        assert row_css_class("asset") == ""
        assert row_css_class("subtotal") == "subtotal"
        assert row_css_class("group_total") == "group-total"
        assert row_css_class("grand_total") == "grand-total"

        # Edge cases
        assert row_css_class("unknown") == ""
        assert row_css_class("") == ""
        assert row_css_class(None) == ""  # type: ignore

    def test_variance_css_class_numeric(self) -> None:
        """Verify variance coloring for numeric inputs."""
        # Positive
        assert variance_css_class(5.0) == "variance-positive"
        assert variance_css_class(Decimal("1.5")) == "variance-positive"
        assert variance_css_class(0.01) == "variance-positive"

        # Negative
        assert variance_css_class(-5.0) == "variance-negative"
        assert variance_css_class(Decimal("-0.01")) == "variance-negative"

        # Zero/Neutral
        assert variance_css_class(0) == ""
        assert variance_css_class(0.0) == ""
        assert variance_css_class(Decimal("0.00")) == ""

    def test_variance_css_class_edge_cases(self) -> None:
        """Verify handling of None and invalid inputs."""
        # None should be handled gracefully
        assert variance_css_class(None) == ""

        # Invalid types that might leak in (though engine should prevent this)
        # These should return empty string rather than crashing
        assert variance_css_class("invalid") == ""  # type: ignore
        assert variance_css_class("+5.2%") == ""  # type: ignore (parsing removed)
        assert variance_css_class([]) == ""  # type: ignore

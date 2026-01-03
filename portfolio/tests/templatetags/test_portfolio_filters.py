"""
Tests for portfolio template filters.

Tests: portfolio/templatetags/portfolio_filters.py
"""

from decimal import Decimal

import pytest

from portfolio.templatetags.portfolio_filters import (
    percentage_of,
)


@pytest.mark.templatetags
@pytest.mark.unit
class TestPortfolioFilters:
    """Tests for accounting-style template filters and percentage calculation."""

    def test_percentage_of(self) -> None:
        """Verify percentage_of calculation."""
        assert percentage_of(50, 200) == Decimal("25")
        assert percentage_of(10, 0) == Decimal("0")
        assert percentage_of("invalid", 100) == Decimal("0")


@pytest.mark.templatetags
@pytest.mark.unit
class TestSimpleFilters:
    """Tests for simple money, percent, and number filters."""

    def test_money_positive(self) -> None:
        """Verify money formatting for positive values."""
        from portfolio.templatetags.portfolio_filters import money

        assert money(1234.56) == "$1,235"
        assert money(1234) == "$1,234"
        assert money(0) == "$0"
        # Test with decimals
        assert money(1234.56, 2) == "$1,234.56"

    def test_money_negative(self) -> None:
        """Verify money formatting for negative values."""
        from portfolio.templatetags.portfolio_filters import money

        assert money(-1234.56) == "($1,235)"
        assert money(-1234) == "($1,234)"
        # Test with decimals
        assert money(-1234.56, 2) == "($1,234.56)"

    def test_money_invalid(self) -> None:
        """Verify money handles invalid inputs."""
        from portfolio.templatetags.portfolio_filters import money

        assert money("invalid") == "invalid"
        assert money(None) == "None"

    def test_percent_default_decimals(self) -> None:
        """Verify percent formatting with default 1 decimal."""
        from portfolio.templatetags.portfolio_filters import percent

        assert percent(12.5) == "12.5%"
        assert percent(-12.5) == "(12.5%)"
        assert percent(0) == "0.0%"

    def test_percent_custom_decimals(self) -> None:
        """Verify percent formatting with custom decimals."""
        from portfolio.templatetags.portfolio_filters import percent

        assert percent(12.345, 2) == "12.35%"
        assert percent(-12.345, 0) == "(12%)"

    def test_number_no_decimals(self) -> None:
        """Verify number formatting with no decimals."""
        from portfolio.templatetags.portfolio_filters import number

        assert number(1234.56) == "1,235"
        assert number(-1234.56) == "(1,235)"

    def test_number_with_decimals(self) -> None:
        """Verify number formatting with decimals."""
        from portfolio.templatetags.portfolio_filters import number

        assert number(1234.567, 2) == "1,234.57"
        assert number(-1234.567, 2) == "(1,234.57)"

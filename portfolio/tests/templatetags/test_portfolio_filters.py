"""
Tests for portfolio template filters.

Tests: portfolio/templatetags/portfolio_filters.py
"""

from decimal import Decimal

import pytest

from portfolio.templatetags.portfolio_filters import (
    accounting_amount,
    accounting_number,
    accounting_percent,
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

    def test_accounting_amount(self) -> None:
        """Verify currency formatting in accounting style."""
        # Note: _format_accounting produces mark_safe strings with hidden span for alignment
        res = accounting_amount(1234.56, 2)
        assert "$1,234.56" in res

        res_neg = accounting_amount(-1234.56, 2)
        assert res_neg == "($1,234.56)"

    def test_accounting_number(self) -> None:
        """Verify number formatting in accounting style."""
        res = accounting_number(1234.567, 2)
        assert "1,234.57" in res

        res_neg = accounting_number(-1234.567, 2)
        assert res_neg == "(1,234.57)"

    def test_accounting_percent(self) -> None:
        """Verify percentage formatting in accounting style."""
        res = accounting_percent(12.34, 1)
        assert "12.3%" in res

        res_neg = accounting_percent(-12.34, 1)
        assert res_neg == "(12.3%)"

    def test_invalid_inputs(self) -> None:
        """Verify handling of invalid numeric inputs."""
        assert accounting_amount("invalid") == "-"
        assert accounting_number(None) == "-"

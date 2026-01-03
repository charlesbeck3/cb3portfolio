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


@pytest.mark.templatetags
@pytest.mark.unit
class TestGetItemFilter:
    """Tests for get_item dictionary lookup filter."""

    def test_get_item_basic(self) -> None:
        """Verify basic dictionary lookup."""
        from portfolio.templatetags.portfolio_filters import get_item

        d = {"a": 1, "b": 2}
        assert get_item(d, "a") == 1
        assert get_item(d, "b") == 2

    def test_get_item_missing_key(self) -> None:
        """Verify missing key returns None."""
        from portfolio.templatetags.portfolio_filters import get_item

        d = {"a": 1}
        assert get_item(d, "missing") is None

    def test_get_item_none_dict(self) -> None:
        """Verify None dictionary returns None."""
        from portfolio.templatetags.portfolio_filters import get_item

        assert get_item(None, "key") is None

    def test_get_item_object_key(self) -> None:
        """Verify object keys work (important for AssetClass lookups)."""
        from portfolio.templatetags.portfolio_filters import get_item

        class MockKey:
            pass

        key = MockKey()
        d = {key: "value"}
        assert get_item(d, key) == "value"


@pytest.mark.templatetags
@pytest.mark.unit
class TestRebalancingFilters:
    """Tests for rebalancing-specific filters."""

    def test_filter_by_asset_class(self) -> None:
        """Verify filtering holdings by asset class."""
        from unittest.mock import Mock

        from portfolio.templatetags.portfolio_filters import filter_by_asset_class

        ac1 = Mock()
        ac1.id = 1
        ac1.name = "AC1"

        ac2 = Mock()
        ac2.id = 2
        ac2.name = "AC2"

        h1 = Mock()
        h1.asset_class = ac1

        h2 = Mock()
        h2.asset_class = ac2

        h3 = Mock()
        h3.asset_class = ac1

        holdings = [h1, h2, h3]

        filtered = filter_by_asset_class(holdings, ac1)
        assert len(filtered) == 2
        assert h1 in filtered
        assert h3 in filtered
        assert h2 not in filtered

        filtered2 = filter_by_asset_class(holdings, ac2)
        assert len(filtered2) == 1
        assert h2 in filtered2

    def test_proforma_subtotal(self) -> None:
        """Verify subtotal calculation."""
        from unittest.mock import Mock

        from portfolio.templatetags.portfolio_filters import proforma_subtotal

        ac1 = Mock()
        ac1.id = 1

        h1 = Mock()
        h1.asset_class = ac1
        h1.current_shares = Decimal("10")
        h1.proforma_shares = Decimal("11")
        h1.current_value = Decimal("100")
        h1.change_value = Decimal("10")
        h1.proforma_value = Decimal("110")
        h1.current_allocation = Decimal("50")
        h1.proforma_allocation = Decimal("50")
        h1.target_allocation = Decimal("50")
        h1.variance = Decimal("0")

        h2 = Mock()
        h2.asset_class = ac1
        h2.current_shares = Decimal("20")
        h2.proforma_shares = Decimal("22")
        h2.current_value = Decimal("200")
        h2.change_value = Decimal("20")
        h2.proforma_value = Decimal("220")
        # Allocations are ignored for h2 as per logic (takes first)

        holdings = [h1, h2]

        subtotal = proforma_subtotal(holdings)

        assert subtotal["current_value"] == 300
        assert subtotal["proforma_value"] == 330
        assert subtotal["current_shares"] == 30
        assert subtotal["proforma_shares"] == 33

        # Check inherited allocations
        assert subtotal["current_allocation"] == 50
        assert subtotal["proforma_allocation"] == 50

    def test_proforma_total(self) -> None:
        """Verify total calculation."""
        from unittest.mock import Mock

        from portfolio.templatetags.portfolio_filters import proforma_total

        h1 = Mock()
        h1.current_value = Decimal("100")
        h1.change_value = Decimal("10")
        h1.proforma_value = Decimal("110")

        h2 = Mock()
        h2.current_value = Decimal("200")
        h2.change_value = Decimal("20")
        h2.proforma_value = Decimal("220")

        holdings = [h1, h2]

        total = proforma_total(holdings)

        assert total["current_value"] == 300
        assert total["proforma_value"] == 330
        assert total["current_allocation"] == 100
        assert total["proforma_allocation"] == 100

    def test_abs_filter(self) -> None:
        """Verify abs filter."""
        from portfolio.templatetags.portfolio_filters import absolute_value

        assert absolute_value(10) == 10
        assert absolute_value(-10) == 10
        assert absolute_value(Decimal("-10.5")) == Decimal("10.5")
        assert absolute_value(0) == 0
        assert absolute_value("invalid") == "invalid"

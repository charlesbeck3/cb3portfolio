"""
Smoke tests for E2E helper utilities.

These tests verify that the helper utilities work correctly
before we use them in real E2E tests.
"""

from decimal import Decimal
from typing import Any

import pytest

from portfolio.tests.e2e.helpers import (
    FinancialDisplayValidator,
    create_allocation_strategy,
    create_test_portfolio_with_values,
)


@pytest.mark.django_db
class TestPortfolioCreationHelper:
    """Test the portfolio creation helper function."""

    def test_create_test_portfolio_helper(
        self,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """Test that portfolio creation helper works with specific values."""
        test_data = create_test_portfolio_with_values(
            test_user,
            base_system_data,
            us_equities_value=50000.0,
            bonds_value=30000.0,
        )

        assert test_data["total_value"] == 80000.0
        assert "VTI" in test_data["holdings"]
        assert "BND" in test_data["holdings"]
        # VTI @ $100/share = 500 shares
        assert test_data["holdings"]["VTI"].shares == Decimal("500.00")
        # BND @ $80/share = 375 shares
        assert test_data["holdings"]["BND"].shares == Decimal("375.00")

    def test_create_test_portfolio_empty(
        self,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """Test creating portfolio with no holdings."""
        test_data = create_test_portfolio_with_values(
            test_user,
            base_system_data,
        )

        assert test_data["total_value"] == 0.0
        assert len(test_data["holdings"]) == 0

    def test_create_test_portfolio_all_asset_classes(
        self,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """Test creating portfolio with all asset types."""
        test_data = create_test_portfolio_with_values(
            test_user,
            base_system_data,
            us_equities_value=10000.0,
            intl_equities_value=5000.0,
            bonds_value=3000.0,
            cash_value=2000.0,
        )

        assert test_data["total_value"] == 20000.0
        assert len(test_data["holdings"]) == 4
        assert "VTI" in test_data["holdings"]
        assert "VXUS" in test_data["holdings"]
        assert "BND" in test_data["holdings"]
        assert "CASH" in test_data["holdings"]


@pytest.mark.django_db
class TestStrategyCreationHelper:
    """Test the strategy creation helper function."""

    def test_create_strategy_helper(
        self,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """Test strategy creation helper."""
        strategy = create_allocation_strategy(
            test_user,
            base_system_data,
            "60/40 Balanced",
            {
                "us_equities": 60.0,
                "cash": 40.0,
            },
        )

        assert strategy.name == "60/40 Balanced"
        targets = strategy.target_allocations.all()
        assert targets.count() == 2

    def test_create_strategy_single_asset(
        self,
        test_user: Any,
        base_system_data: Any,
    ) -> None:
        """Test creating strategy with single asset class."""
        strategy = create_allocation_strategy(
            test_user,
            base_system_data,
            "All Cash",
            {"cash": 100.0},
        )

        assert strategy.name == "All Cash"
        targets = strategy.target_allocations.all()
        assert targets.count() == 1


class TestFinancialDisplayValidator:
    """Test the financial display validator class (no DB required)."""

    def test_money_pattern_valid(self) -> None:
        """Test that valid money patterns match."""
        import re

        pattern = FinancialDisplayValidator.MONEY_PATTERN
        assert re.match(pattern, "$50,000")
        assert re.match(pattern, "$1,000")
        assert re.match(pattern, "$100")
        assert re.match(pattern, "($5,000)")

    def test_money_pattern_invalid(self) -> None:
        """Test that invalid money patterns don't match."""
        import re

        pattern = FinancialDisplayValidator.MONEY_PATTERN
        assert not re.match(pattern, "50000")
        assert not re.match(pattern, "NaN")
        assert not re.match(pattern, "$NaN")

    def test_percent_pattern_valid(self) -> None:
        """Test that valid percent patterns match."""
        import re

        pattern = FinancialDisplayValidator.PERCENT_PATTERN
        assert re.match(pattern, "50.0%")
        assert re.match(pattern, "10.5%")
        assert re.match(pattern, "-5.0%")
        assert re.match(pattern, "(5.0%)")

    def test_percent_pattern_invalid(self) -> None:
        """Test that invalid percent patterns don't match."""
        import re

        pattern = FinancialDisplayValidator.PERCENT_PATTERN
        assert not re.match(pattern, "50")
        assert not re.match(pattern, "NaN%")
        assert not re.match(pattern, "undefined")


@pytest.mark.e2e
class TestFinancialDisplayValidatorWithPlaywright:
    """Test validator with Playwright (requires browser)."""

    def test_validator_detects_invalid_values(
        self,
        page: Any,
    ) -> None:
        """Test that validator detects invalid values in HTML."""
        # Create test page with NaN
        page.set_content("<div>Value: NaN</div>")

        validator = FinancialDisplayValidator()

        # Should raise AssertionError
        with pytest.raises(AssertionError, match="invalid value 'NaN'"):
            validator.assert_no_invalid_values(page)

    def test_validator_passes_on_valid_page(
        self,
        page: Any,
    ) -> None:
        """Test that validator passes on valid content."""
        # Create test page with valid money
        page.set_content("<div>Value: $50,000</div>")

        validator = FinancialDisplayValidator()

        # Should not raise
        validator.assert_no_invalid_values(page)

    def test_money_format_validation(
        self,
        page: Any,
    ) -> None:
        """Test money format validation."""
        validator = FinancialDisplayValidator()

        # Valid formats
        page.set_content('<div id="valid">$50,000</div>')
        locator = page.locator("#valid")
        validator.assert_valid_money_format(locator)  # Should pass

        # Invalid format
        page.set_content('<div id="invalid">50000</div>')
        locator = page.locator("#invalid")

        with pytest.raises(AssertionError, match="Invalid money format"):
            validator.assert_valid_money_format(locator)

    def test_get_money_value(
        self,
        page: Any,
    ) -> None:
        """Test extracting numeric value from money string."""
        validator = FinancialDisplayValidator()

        # Positive value
        page.set_content('<div id="pos">$50,000</div>')
        value = validator.get_money_value(page.locator("#pos"))
        assert value == 50000.0

        # Negative value
        page.set_content('<div id="neg">($1,000)</div>')
        value = validator.get_money_value(page.locator("#neg"))
        assert value == -1000.0

    def test_get_percent_value(
        self,
        page: Any,
    ) -> None:
        """Test extracting numeric value from percent string."""
        validator = FinancialDisplayValidator()

        # Positive value
        page.set_content('<div id="pos">50.0%</div>')
        value = validator.get_percent_value(page.locator("#pos"))
        assert value == 50.0

        # Negative value (with minus sign)
        page.set_content('<div id="neg">-5.0%</div>')
        value = validator.get_percent_value(page.locator("#neg"))
        assert value == -5.0

        # Negative value (with parentheses)
        page.set_content('<div id="neg2">(5.0%)</div>')
        value = validator.get_percent_value(page.locator("#neg2"))
        assert value == -5.0

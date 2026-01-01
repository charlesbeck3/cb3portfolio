"""
E2E testing utilities for financial data validation.

This module provides helper classes and functions for validating
financial displays in end-to-end tests with Playwright.
"""

import re
from decimal import Decimal
from typing import Any

from django.utils import timezone

from playwright.sync_api import Locator, Page


class FinancialDisplayValidator:
    """
    Helper class for validating financial displays in E2E tests.

    Usage:
        validator = FinancialDisplayValidator()
        validator.assert_no_invalid_values(page)
        validator.assert_valid_money_format(locator)
    """

    # Invalid value patterns that should never appear
    INVALID_PATTERNS = [
        "NaN",
        "undefined",
        "null",
        "Infinity",
        "-Infinity",
        "$NaN",
        "$undefined",
        "$null",
    ]

    # Valid format patterns
    MONEY_PATTERN = r"^\$[\d,]+$|^\(\$[\d,]+\)$"
    PERCENT_PATTERN = r"^-?[\d.]+%$|^\([\d.]+%\)$"

    @staticmethod
    def assert_no_invalid_values(page: Page) -> None:
        """
        Assert page contains no NaN, undefined, null, or Infinity values.

        This is the most critical validation - financial apps should
        never display these error values to users.

        Args:
            page: Playwright page object

        Raises:
            AssertionError: If any invalid values are found
        """
        for pattern in FinancialDisplayValidator.INVALID_PATTERNS:
            count = page.locator(f"text={pattern}").count()
            assert count == 0, f"Found {count} instances of invalid value '{pattern}' on page"

    @staticmethod
    def assert_valid_money_format(locator: Locator) -> None:
        """
        Assert locator contains properly formatted currency.

        Valid formats:
        - $1,000
        - $50,000
        - ($1,000) for negatives

        Args:
            locator: Playwright locator

        Raises:
            AssertionError: If format is invalid
        """
        text = locator.text_content()
        assert text is not None, "Locator has no text content"
        text = text.strip()

        assert re.match(FinancialDisplayValidator.MONEY_PATTERN, text), (
            f"Invalid money format: '{text}'. Expected format: $X,XXX or ($X,XXX)"
        )

    @staticmethod
    def assert_valid_percent_format(locator: Locator) -> None:
        """
        Assert locator contains properly formatted percentage.

        Valid formats:
        - 50.0%
        - 10.5%
        - -5.0% for negatives
        - (5.0%) for negatives (parentheses style)

        Args:
            locator: Playwright locator

        Raises:
            AssertionError: If format is invalid
        """
        text = locator.text_content()
        assert text is not None, "Locator has no text content"
        text = text.strip()

        assert re.match(FinancialDisplayValidator.PERCENT_PATTERN, text), (
            f"Invalid percent format: '{text}'. Expected format: X.X% or (X.X%)"
        )

    @staticmethod
    def assert_variance_has_color(locator: Locator) -> None:
        """
        Assert variance cell has appropriate CSS class.

        Variance cells should have either:
        - variance-positive (for over-target)
        - variance-negative (for under-target)

        Args:
            locator: Playwright locator

        Raises:
            AssertionError: If color class is missing
        """
        classes = locator.get_attribute("class")
        assert classes is not None, "Locator has no class attribute"

        has_color = "variance-positive" in classes or "variance-negative" in classes

        assert has_color, f"Variance cell missing color class. Classes: {classes}"

    @staticmethod
    def get_money_value(locator: Locator) -> float:
        """
        Extract numeric value from formatted money string.

        Examples:
        - "$50,000" -> 50000.0
        - "($1,000)" -> -1000.0

        Args:
            locator: Playwright locator

        Returns:
            Numeric value as float
        """
        text = locator.text_content()
        assert text is not None, "Locator has no text content"

        # Check if negative (wrapped in parentheses)
        is_negative = text.startswith("(") and text.endswith(")")

        # Remove $, commas, and parentheses
        cleaned = re.sub(r"[\$,\(\)]", "", text)
        value = float(cleaned)

        return -value if is_negative else value

    @staticmethod
    def get_percent_value(locator: Locator) -> float:
        """
        Extract numeric value from formatted percentage string.

        Examples:
        - "50.0%" -> 50.0
        - "-5.0%" -> -5.0
        - "(5.0%)" -> -5.0

        Args:
            locator: Playwright locator

        Returns:
            Numeric value as float (percentage points, not decimal)
        """
        text = locator.text_content()
        assert text is not None, "Locator has no text content"

        # Check if negative (wrapped in parentheses)
        is_negative = text.startswith("(") and text.endswith(")")

        # Remove %, parentheses
        cleaned = re.sub(r"[%\(\)]", "", text)
        value = float(cleaned)

        return -value if is_negative else value


def create_test_portfolio_with_values(
    test_user: Any,
    base_system_data: Any,
    us_equities_value: float = 0.0,
    intl_equities_value: float = 0.0,
    bonds_value: float = 0.0,
    cash_value: float = 0.0,
) -> dict[str, Any]:
    """
    Create a test portfolio with specific values for E2E testing.

    This is the primary fixture for creating test data for E2E tests.
    It creates a portfolio with holdings that have exact known values.

    Args:
        test_user: Django user object
        base_system_data: Fixture with securities and account types
        us_equities_value: Dollar value of US equities holdings
        intl_equities_value: Dollar value of international equities
        bonds_value: Dollar value of bond holdings
        cash_value: Dollar value of cash holdings

    Returns:
        dict with:
        - portfolio: Portfolio object
        - account: Account object
        - holdings: Dict of ticker -> Holding object
        - total_value: Sum of all holdings
        - prices: Dict of ticker -> price used

    Example:
        test_data = create_test_portfolio_with_values(
            test_user,
            base_system_data,
            us_equities_value=50000.0,
            bonds_value=30000.0
        )
        # Creates portfolio with $50k in VTI, $30k in BND
    """
    from portfolio.models import Account, Holding, Portfolio, SecurityPrice

    portfolio = Portfolio.objects.create(user=test_user, name="E2E Test Portfolio")

    account = Account.objects.create(
        user=test_user,
        name="E2E Test Account",
        portfolio=portfolio,
        account_type=base_system_data.type_taxable,
        institution=base_system_data.institution,
    )

    holdings: dict[str, Holding] = {}
    prices: dict[str, float] = {}
    now = timezone.now()

    # Create US Equities holding (VTI @ $100/share)
    if us_equities_value > 0:
        price = Decimal("100.00")
        shares = Decimal(str(us_equities_value)) / price

        holdings["VTI"] = Holding.objects.create(
            account=account, security=base_system_data.vti, shares=shares
        )

        SecurityPrice.objects.update_or_create(
            security=base_system_data.vti,
            defaults={"price": price, "price_datetime": now, "source": "test"},
        )

        prices["VTI"] = float(price)

    # Create International Equities holding (VXUS @ $50/share)
    if intl_equities_value > 0:
        price = Decimal("50.00")
        shares = Decimal(str(intl_equities_value)) / price

        holdings["VXUS"] = Holding.objects.create(
            account=account, security=base_system_data.vxus, shares=shares
        )

        SecurityPrice.objects.update_or_create(
            security=base_system_data.vxus,
            defaults={"price": price, "price_datetime": now, "source": "test"},
        )

        prices["VXUS"] = float(price)

    # Create Bond holding (BND @ $80/share)
    if bonds_value > 0:
        price = Decimal("80.00")
        shares = Decimal(str(bonds_value)) / price

        holdings["BND"] = Holding.objects.create(
            account=account, security=base_system_data.bnd, shares=shares
        )

        SecurityPrice.objects.update_or_create(
            security=base_system_data.bnd,
            defaults={"price": price, "price_datetime": now, "source": "test"},
        )

        prices["BND"] = float(price)

    # Create Cash holding (CASH @ $1/share)
    if cash_value > 0:
        price = Decimal("1.00")
        shares = Decimal(str(cash_value)) / price

        holdings["CASH"] = Holding.objects.create(
            account=account, security=base_system_data.cash, shares=shares
        )

        SecurityPrice.objects.update_or_create(
            security=base_system_data.cash,
            defaults={"price": price, "price_datetime": now, "source": "test"},
        )

        prices["CASH"] = float(price)

    total_value = us_equities_value + intl_equities_value + bonds_value + cash_value

    return {
        "portfolio": portfolio,
        "account": account,
        "holdings": holdings,
        "total_value": total_value,
        "prices": prices,
    }


def create_allocation_strategy(
    test_user: Any,
    base_system_data: Any,
    name: str,
    allocations: dict[str, float],
) -> Any:
    """
    Create an AllocationStrategy with specified targets.

    Args:
        test_user: Django user object
        base_system_data: Fixture with asset classes
        name: Strategy name
        allocations: Dict of asset_class_code -> target_percent
            Example: {'us_equities': 60.0, 'cash': 40.0}

    Returns:
        AllocationStrategy object

    Example:
        strategy = create_allocation_strategy(
            test_user,
            base_system_data,
            "60/40 Balanced",
            {'us_equities': 60.0, 'cash': 40.0}
        )
    """
    from portfolio.models import AllocationStrategy

    strategy = AllocationStrategy.objects.create(user=test_user, name=name)

    # Convert asset class codes to IDs and create targets
    target_dict: dict[int, Decimal] = {}
    for code, percent in allocations.items():
        # Get asset class by code from base_system_data
        asset_class = getattr(base_system_data, f"asset_class_{code.lower()}", None)
        if asset_class:
            target_dict[asset_class.id] = Decimal(str(percent))

    strategy.save_allocations(target_dict)

    return strategy

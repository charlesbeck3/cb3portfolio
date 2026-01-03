"""
Root-level pytest fixtures for portfolio test suite.

Fixture Hierarchy:
- base_system_data: System-wide seed data (account types, asset classes, etc.)
- test_user: Standard test user
- test_portfolio: Portfolio with user and system data
- simple_holdings: Portfolio with $1000 VTI in Roth IRA
- multi_account_holdings: Roth + Taxable accounts with holdings
- standard_test_portfolio: Backward-compatible fixture for E2E tests

Mock Fixtures (imported from fixtures/mocks.py):
- mock_market_prices: Factory for custom price mocking
- stable_test_prices: Pre-configured standard test prices
- zero_prices: Empty prices for edge case testing
- volatile_prices: Extreme prices for stress testing
"""

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest

from portfolio.models import (
    Account,
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Holding,
    Institution,
    Portfolio,
    Security,
)
from portfolio.tests import factories
from portfolio.tests.fixtures.benchmarks import (
    large_portfolio_benchmark,
    medium_portfolio_benchmark,
)
from portfolio.tests.fixtures.golden_reference import golden_reference_portfolio

# Import mock fixtures to make them available globally
from portfolio.tests.fixtures.mocks import (
    mock_market_prices,
    stable_test_prices,
    volatile_prices,
    zero_prices,
)

User = get_user_model()

# Export all fixtures for better IDE autocomplete and documentation
__all__ = [
    # System data
    "base_system_data",
    # Users
    "test_user",
    "test_user_with_name",
    # Portfolios
    "test_portfolio",
    "roth_account",
    "taxable_account",
    # Holdings
    "simple_holdings",
    "multi_account_holdings",
    "standard_test_portfolio",
    # Golden reference
    "golden_reference_portfolio",
    # Mock fixtures
    "mock_market_prices",
    "stable_test_prices",
    "zero_prices",
    "volatile_prices",
    # Benchmark fixtures
    "large_portfolio_benchmark",
    "medium_portfolio_benchmark",
    # Factories
    "factories",
]


# ============================================================================
# SYSTEM DATA FIXTURES
# ============================================================================


@pytest.fixture
def base_system_data(db: Any) -> Any:
    """
    Seed system-wide data and return mixin-like object for easy access.

    This replaces PortfolioTestMixin.setup_system_data() for pytest tests.
    Provides access to standard institutions, account types, and asset classes.

    Returns:
        Object with attributes for all system data (institutions, types, categories, etc.)
    """
    from portfolio.services.seeder import SystemSeederService

    # Run the centralized seeder
    seeder = SystemSeederService()
    seeder.run()

    from types import SimpleNamespace

    # Create a simple namespace object to hold references
    data: Any = SimpleNamespace()

    # Populate Institution
    data.institution = Institution.objects.get(name="Vanguard")

    # Populate Groups
    data.group_retirement = AccountGroup.objects.get(name="Retirement")
    data.group_investments = AccountGroup.objects.get(name="Investments")
    data.group_deposits = AccountGroup.objects.get(name="Deposits")

    # Populate Account Types
    data.type_roth = AccountType.objects.get(code="ROTH_IRA")
    data.type_trad = AccountType.objects.get(code="TRADITIONAL_IRA")
    data.type_taxable = AccountType.objects.get(code="TAXABLE")
    data.type_401k = AccountType.objects.get(code="401K")
    data.type_deposit = AccountType.objects.get(code="DEPOSIT")

    # Populate Asset Categories
    data.cat_equities = AssetClassCategory.objects.get(code="EQUITIES")
    data.cat_fixed_income = AssetClassCategory.objects.get(code="FIXED_INCOME")
    data.cat_cash = AssetClassCategory.objects.get(code="CASH")
    data.cat_us_eq = AssetClassCategory.objects.get(code="US_EQUITIES")
    data.cat_intl_eq = AssetClassCategory.objects.get(code="INTERNATIONAL_EQUITIES")
    data.cat_fi = AssetClassCategory.objects.get(code="FIXED_INCOME")

    # Populate Asset Classes
    data.asset_class_us_equities = AssetClass.objects.get(name="US Equities")
    data.asset_class_intl_developed = AssetClass.objects.get(
        name="International Developed Equities"
    )
    data.asset_class_intl_emerging = AssetClass.objects.get(name="International Emerging Equities")
    data.asset_class_treasuries_short = AssetClass.objects.get(name="US Treasuries - Short")
    data.asset_class_treasuries_interm = AssetClass.objects.get(name="US Treasuries - Intermediate")
    data.asset_class_tips = AssetClass.objects.get(name="Inflation Adjusted Bond")
    data.asset_class_cash = AssetClass.objects.get(name=AssetClass.CASH_NAME)

    # Populate Securities
    data.vti = Security.objects.get(ticker="VTI")
    data.vxus = Security.objects.get(ticker="VXUS")
    data.bnd = Security.objects.get(ticker="BND")
    data.vgsh = Security.objects.get(ticker="VGSH")
    data.cash = Security.objects.get(ticker="CASH")

    return data


# ============================================================================
# ASSET CLASS FIXTURES
# ============================================================================


@pytest.fixture
def international_stocks(base_system_data: Any) -> Any:
    """International Stocks asset class."""
    return base_system_data.asset_class_intl_developed


# ============================================================================
# USER FIXTURES
# ============================================================================


@pytest.fixture
def test_user(db: Any) -> Any:
    """
    Standard test user - reusable across all tests.

    Username: testuser
    Password: password
    """
    return User.objects.create_user(username="testuser", password="password")


@pytest.fixture
def test_user_with_name(db: Any) -> Any:
    """Test user with custom username - for multi-user test scenarios."""

    def _create_user(username: str, password: str = "password") -> Any:  # noqa: S107
        return User.objects.create_user(username=username, password=password)

    return _create_user


# ============================================================================
# PORTFOLIO FIXTURES
# ============================================================================


@pytest.fixture
def test_portfolio(db: Any, test_user: Any, base_system_data: Any) -> dict[str, Any]:
    """
    Standard portfolio with user and system data.

    Returns dict with:
    - user: Test user
    - portfolio: Empty portfolio
    - system: System data object
    """
    portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")

    return {
        "user": test_user,
        "portfolio": portfolio,
        "system": base_system_data,
    }


@pytest.fixture
def roth_account(test_portfolio: dict[str, Any]) -> Account:
    """
    Single Roth IRA account (no holdings).

    Requires: test_portfolio fixture
    """
    system = test_portfolio["system"]
    return Account.objects.create(
        user=test_portfolio["user"],
        name="Roth IRA",
        portfolio=test_portfolio["portfolio"],
        account_type=system.type_roth,
        institution=system.institution,
    )


@pytest.fixture
def taxable_account(test_portfolio: dict[str, Any]) -> Account:
    """
    Single taxable account (no holdings).

    Requires: test_portfolio fixture
    """
    system = test_portfolio["system"]
    return Account.objects.create(
        user=test_portfolio["user"],
        name="Taxable Brokerage",
        portfolio=test_portfolio["portfolio"],
        account_type=system.type_taxable,
        institution=system.institution,
    )


# ============================================================================
# HOLDINGS FIXTURES
# ============================================================================


@pytest.fixture
def simple_holdings(test_portfolio: dict[str, Any], roth_account: Account) -> dict[str, Any]:
    """
    Simple portfolio with one Roth IRA holding $1000 VTI.

    Returns dict with all created objects.
    """
    system = test_portfolio["system"]

    holding = Holding.objects.create(
        account=roth_account,
        security=system.vti,
        shares=Decimal("10"),
    )

    from django.utils import timezone

    from portfolio.models import SecurityPrice

    SecurityPrice.objects.create(
        security=system.vti, price=Decimal("100"), price_datetime=timezone.now(), source="manual"
    )

    return {
        **test_portfolio,
        "account": roth_account,
        "holding": holding,
        "system": system,
    }


@pytest.fixture
def multi_account_holdings(
    test_portfolio: dict[str, Any], roth_account: Account, taxable_account: Account
) -> dict[str, Any]:
    """
    Portfolio with holdings in both Roth and Taxable accounts.

    Roth: $600 VTI
    Taxable: $400 BND
    Total: $1000
    """
    system = test_portfolio["system"]

    roth_holding = Holding.objects.create(
        account=roth_account,
        security=system.vti,
        shares=Decimal("6"),
    )

    from django.utils import timezone

    from portfolio.models import SecurityPrice

    # Price for VTI (matches simple_holdings but just to be sure)
    SecurityPrice.objects.update_or_create(
        security=system.vti,
        defaults={"price": Decimal("100"), "price_datetime": timezone.now(), "source": "manual"},
    )

    taxable_holding = Holding.objects.create(
        account=taxable_account,
        security=system.bnd,
        shares=Decimal("4"),
    )

    # Price for BND
    SecurityPrice.objects.update_or_create(
        security=system.bnd,
        defaults={"price": Decimal("100"), "price_datetime": timezone.now(), "source": "manual"},
    )

    return {
        **test_portfolio,
        "roth_account": roth_account,
        "taxable_account": taxable_account,
        "roth_holding": roth_holding,
        "taxable_holding": taxable_holding,
        "system": system,
    }


# ============================================================================
# BACKWARD COMPATIBILITY (For E2E Tests)
# ============================================================================


@pytest.fixture
def standard_test_portfolio(simple_holdings: dict[str, Any]) -> dict[str, Any]:
    """
    Backward-compatible fixture for E2E tests.

    Creates the same structure as the old standard_test_portfolio fixture.
    This allows existing E2E tests to continue working unchanged.
    """
    # Transform simple_holdings format to match old structure
    return {
        "mixin": simple_holdings["system"],  # system data acts like mixin
        "user": simple_holdings["user"],
        "portfolio": simple_holdings["portfolio"],
        "us_stocks": simple_holdings["system"].asset_class_us_equities,
        "account": simple_holdings["account"],
        "holding": simple_holdings["holding"],
    }

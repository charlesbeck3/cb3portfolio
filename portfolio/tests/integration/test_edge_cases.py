"""
Test edge cases and boundary conditions for portfolio calculations.
"""

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

import pytest

from portfolio.models import (
    Account,
    AllocationStrategy,
    Holding,
    Portfolio,
    Security,
    SecurityPrice,
    TargetAllocation,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine


@pytest.mark.models
@pytest.mark.integration
class TestZeroBalanceHandling:
    """Tests for accounts and holdings with zero balances."""

    def test_account_with_zero_balance(self, test_user: Any, base_system_data: Any) -> None:
        """Test that accounts with zero balance are handled correctly."""
        system = base_system_data
        portfolio = Portfolio.objects.create(name="Test Portfolio", user=test_user)
        Account.objects.create(
            portfolio=portfolio,
            user=test_user,
            name="Empty Account",
            account_type=system.type_taxable,
            institution=system.institution,
        )

        engine = AllocationCalculationEngine()
        result = engine.calculate_allocations(portfolio.to_dataframe())

        # Check total value in summary
        summary = result["portfolio_summary"]
        val = Decimal("0.00") if summary.empty else Decimal(str(summary["total_value"].iloc[0]))
        assert val == Decimal("0.00")

    def test_holding_with_zero_shares(self, test_user: Any, base_system_data: Any) -> None:
        """Test that holdings with zero shares are handled correctly."""
        system = base_system_data
        portfolio = Portfolio.objects.create(name="Test Portfolio", user=test_user)
        account = Account.objects.create(
            portfolio=portfolio,
            user=test_user,
            name="Test Account",
            account_type=system.type_taxable,
            institution=system.institution,
        )
        security = Security.objects.create(
            ticker="VTI_ZERO",
            name="Vanguard Total Stock Market Zero",
            asset_class=system.cat_us_eq.asset_classes.create(name="US Equities Zero Shares"),
        )
        # Create holding with zero shares
        Holding.objects.create(
            account=account,
            security=security,
            shares=Decimal("0"),
        )

        # Create price
        now = timezone.now()
        SecurityPrice.objects.create(
            security=security, price=Decimal("100.00"), price_datetime=now, source="manual"
        )

        engine = AllocationCalculationEngine()
        result = engine.calculate_allocations(portfolio.to_dataframe())

        summary = result["portfolio_summary"]
        val = Decimal("0.00") if summary.empty else Decimal(str(summary["total_value"].iloc[0]))
        assert val == Decimal("0.00")


@pytest.mark.models
@pytest.mark.integration
class TestAllZeroAllocations:
    """Tests for portfolios with all zero target allocations."""

    def test_all_zero_target_allocations(self, test_user: Any, base_system_data: Any) -> None:
        """Test portfolio with all zero target allocations."""
        system = base_system_data
        portfolio = Portfolio.objects.create(name="Test Portfolio", user=test_user)
        strategy = AllocationStrategy.objects.create(name="Zero Strategy", user=test_user)

        asset_class = system.cat_us_eq.asset_classes.create(name="US Equities Zero")

        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=asset_class,
            target_percent=Decimal("0.00"),
        )

        # Assign strategy to portfolio
        portfolio.allocation_strategy = strategy

        # Should raise ValidationError because sum is 0%
        with pytest.raises(ValidationError) as exc_info:
            portfolio.save()

        assert "allocation_strategy" in exc_info.value.message_dict
        assert "100" in str(exc_info.value)


@pytest.mark.models
@pytest.mark.integration
class TestInvalidPriceData:
    """Tests for handling invalid or missing price data."""

    def test_negative_price_validation(self, test_user: Any, base_system_data: Any) -> None:
        """Test that negative prices are rejected in SecurityPrice."""
        system = base_system_data
        account = Account.objects.create(
            name="Test Account",
            portfolio=Portfolio.objects.create(name="P", user=test_user),
            user=test_user,
            account_type=system.type_taxable,
            institution=system.institution,
        )

        # Create holding (no price validation here anymore)
        Holding.objects.create(
            account=account,
            security=system.vti,
            shares=Decimal("10"),
        )

        # Test negative price in SecurityPrice
        now = timezone.now()
        price = SecurityPrice(
            security=system.vti, price=Decimal("-50.00"), price_datetime=now, source="manual"
        )

        with pytest.raises(ValidationError) as exc_info:
            price.full_clean()

        assert "price" in exc_info.value.message_dict


@pytest.mark.models
@pytest.mark.integration
class TestNegativeShares:
    """Tests for negative share counts."""

    def test_negative_shares_validation(self, test_user: Any, base_system_data: Any) -> None:
        """Test that negative shares are rejected."""
        system = base_system_data
        account = Account.objects.create(
            name="Test Account",
            portfolio=Portfolio.objects.create(name="P", user=test_user),
            user=test_user,
            account_type=system.type_taxable,
            institution=system.institution,
        )

        with pytest.raises(ValidationError) as exc_info:
            holding = Holding(
                account=account,
                security=system.vti,
                shares=Decimal("-100"),
            )
            holding.full_clean()

        assert "shares" in exc_info.value.message_dict


@pytest.mark.models
@pytest.mark.integration
class TestEmptyPortfolio:
    """Tests for completely empty portfolios."""

    def test_portfolio_with_no_accounts(self, test_user: Any) -> None:
        """Test portfolio with no accounts."""
        portfolio = Portfolio.objects.create(name="Empty Portfolio", user=test_user)

        engine = AllocationCalculationEngine()
        result = engine.calculate_allocations(portfolio.to_dataframe())

        summary = result["portfolio_summary"]
        val = Decimal("0.00") if summary.empty else Decimal(str(summary["total_value"].iloc[0]))
        assert val == Decimal("0.00")

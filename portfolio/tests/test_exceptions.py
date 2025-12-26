from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model

import pytest

from portfolio.exceptions import (
    AllocationError,
    CalculationError,
    OptimizationError,
    PortfolioError,
    PricingError,
)
from portfolio.models import AllocationStrategy, AssetClass

User = get_user_model()


class TestExceptionHierarchy:
    def test_portfolio_error_base(self) -> None:
        """Test that PortfolioError is the base class."""
        assert issubclass(PortfolioError, Exception)

    def test_allocation_error_inheritance(self) -> None:
        """Test AllocationError inheritance."""
        assert issubclass(AllocationError, PortfolioError)

    def test_calculation_error_inheritance(self) -> None:
        """Test CalculationError inheritance."""
        assert issubclass(AllocationError, PortfolioError)
        # Wait, I noticed a copypasta error in previous iteration while looking at it
        # Inheritance check was correct in logic but maybe I should fix the name in comment/body if needed
        # Actually it was checking AllocationError instead of CalculationError in my thought?
        # Let's fix it properly.
        assert issubclass(CalculationError, PortfolioError)

    def test_pricing_error_inheritance(self) -> None:
        """Test PricingError inheritance."""
        assert issubclass(PricingError, PortfolioError)

    def test_optimization_error_inheritance(self) -> None:
        """Test OptimizationError inheritance."""
        assert issubclass(OptimizationError, PortfolioError)


@pytest.mark.django_db
class TestAllocationStrategyExceptions:
    @pytest.fixture
    def user(self) -> Any:
        return User.objects.create_user(username="testuser_exceptions", password="password")

    @pytest.fixture
    def strategy(self, user: Any) -> AllocationStrategy:
        return AllocationStrategy.objects.create(name="Test Strategy", user=user)

    @pytest.fixture
    def cash_asset(self) -> AssetClass:
        # Ensure cash exists
        # Wait, AssetClass structure is complex.
        # Let's use the fixture or create minimal.
        # Actually proper way is to look at AssetClass model constraints
        from portfolio.models import AssetClassCategory

        category, _ = AssetClassCategory.objects.get_or_create(
            code="CASH", label="Cash", sort_order=0
        )
        cash, _ = AssetClass.objects.get_or_create(
            name="Cash",
            defaults={
                "category": category,
            },
        )
        return cash

    @pytest.fixture
    def stock_asset(self) -> AssetClass:
        from portfolio.models import AssetClassCategory

        category, _ = AssetClassCategory.objects.get_or_create(
            code="AC", label="Asset Class", sort_order=1
        )
        stock, _ = AssetClass.objects.get_or_create(
            name="Test Stock",
            defaults={
                "category": category,
            },
        )
        return stock

    def test_save_allocations_raises_allocation_error_explicit_cash(
        self, strategy: AllocationStrategy, cash_asset: AssetClass, stock_asset: AssetClass
    ) -> None:
        """Test that save_allocations raises AllocationError when explicit cash sum is wrong."""
        allocations = {
            stock_asset.id: Decimal("50.00"),
            cash_asset.id: Decimal("40.00"),  # Sums to 90%, should be 100%
        }

        with pytest.raises(AllocationError) as excinfo:
            strategy.save_allocations(allocations)

        assert "Allocations sum to 90.00%" in str(excinfo.value)
        assert "Cash is explicitly provided" in str(excinfo.value)

    def test_save_allocations_raises_allocation_error_excess_total(
        self, strategy: AllocationStrategy, stock_asset: AssetClass, cash_asset: AssetClass
    ) -> None:
        """Test that save_allocations raises AllocationError when total > 100%."""
        allocations = {stock_asset.id: Decimal("110.00")}

        with pytest.raises(AllocationError) as excinfo:
            strategy.save_allocations(allocations)

        assert "exceeds 100%" in str(excinfo.value)

    def test_save_allocations_valid(
        self, strategy: AllocationStrategy, stock_asset: AssetClass, cash_asset: AssetClass
    ) -> None:
        """Test that valid allocations work."""
        allocations = {stock_asset.id: Decimal("100.00")}
        # Should not raise
        strategy.save_allocations(allocations)

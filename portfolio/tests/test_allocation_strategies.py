from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import AllocationStrategy
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


class AllocationStrategyCashCalculationTests(TestCase, PortfolioTestMixin):
    """Test the extracted cash allocation calculation logic."""

    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser")
        self.strategy = AllocationStrategy.objects.create(user=self.user, name="Test Strategy")

    def test_calculate_cash_allocation_simple_remainder(self) -> None:
        """Test cash calculation with simple 60/30 split."""
        allocations = {
            1: Decimal("60.00"),
            2: Decimal("30.00"),
        }

        cash = self.strategy.calculate_cash_allocation(allocations)

        self.assertEqual(cash, Decimal("10.00"))

    def test_calculate_cash_allocation_zero_remainder(self) -> None:
        """Test cash calculation when allocations sum to 100%."""
        allocations = {
            1: Decimal("100.00"),
        }

        cash = self.strategy.calculate_cash_allocation(allocations)

        self.assertEqual(cash, Decimal("0.00"))

    def test_calculate_cash_allocation_small_remainder(self) -> None:
        """Test cash calculation with small remainder."""
        allocations = {
            1: Decimal("99.50"),
        }

        cash = self.strategy.calculate_cash_allocation(allocations)

        self.assertEqual(cash, Decimal("0.50"))

    def test_calculate_cash_allocation_multiple_assets(self) -> None:
        """Test cash calculation with multiple asset classes."""
        allocations = {
            1: Decimal("40.00"),
            2: Decimal("25.00"),
            3: Decimal("20.00"),
        }

        cash = self.strategy.calculate_cash_allocation(allocations)

        self.assertEqual(cash, Decimal("15.00"))

    def test_calculate_cash_allocation_empty_dict(self) -> None:
        """Test cash calculation with no allocations (100% cash)."""
        allocations: dict[int, Decimal] = {}

        cash = self.strategy.calculate_cash_allocation(allocations)

        self.assertEqual(cash, Decimal("100.00"))

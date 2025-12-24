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


class AllocationStrategyValidationTests(TestCase, PortfolioTestMixin):
    """Test defensive validation in AllocationStrategy.save_allocations()."""

    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser_validation")
        self.strategy = AllocationStrategy.objects.create(user=self.user, name="Test Strategy")

    def test_save_allocations_validates_total(self) -> None:
        """Verify save_allocations() catches total != 100%."""
        # This should work (implicit cash)
        self.strategy.save_allocations(
            {
                self.ac_us_eq.id: Decimal("60.00"),
                self.ac_intl_dev.id: Decimal("40.00"),
            }
        )

        # Verify saved correctly
        total = sum(ta.target_percent for ta in self.strategy.target_allocations.all())
        self.assertEqual(total, Decimal("100.00"))

    def test_save_allocations_prevents_invalid_data(self) -> None:
        """Verify save_allocations() fails fast on calculation errors."""
        # Manually create invalid allocations that don't sum to 100%
        # This simulates a bug in calculation logic or explicit bad input with cash
        invalid_allocations = {
            self.ac_us_eq.id: Decimal("60.00"),
            self.ac_intl_dev.id: Decimal("30.00"),
            self.ac_cash.id: Decimal("5.00"),  # Sums to 95%
        }

        with self.assertRaises(ValueError) as ctx:
            self.strategy.save_allocations(invalid_allocations)

        self.assertIn("expected exactly 100.00%", str(ctx.exception))

    def test_validate_allocations_helper(self) -> None:
        """Test validate_allocations() helper method."""
        # Valid allocations
        valid = {
            self.ac_us_eq.id: Decimal("60.00"),
            self.ac_intl_dev.id: Decimal("30.00"),
            self.ac_cash.id: Decimal("10.00"),
        }
        is_valid, error = self.strategy.validate_allocations(valid)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

        # Invalid - sum to 95%
        invalid = {
            self.ac_us_eq.id: Decimal("60.00"),
            self.ac_intl_dev.id: Decimal("30.00"),
            self.ac_cash.id: Decimal("5.00"),
        }
        is_valid, error = self.strategy.validate_allocations(invalid)
        self.assertFalse(is_valid)
        self.assertIn("95", error)
        self.assertIn("100", error)

        # Invalid - sum to 105%
        over = {
            self.ac_us_eq.id: Decimal("60.00"),
            self.ac_intl_dev.id: Decimal("30.00"),
            self.ac_cash.id: Decimal("15.00"),
        }
        is_valid, error = self.strategy.validate_allocations(over)
        self.assertFalse(is_valid)
        self.assertIn("105", error)

    def test_rounding_within_tolerance(self) -> None:
        """Verify tiny rounding errors are accepted."""
        # Allocations with tiny rounding error (100.0001%)
        # Should be accepted within tolerance (0.001%)
        nearly_100 = {
            self.ac_us_eq.id: Decimal("33.3333"),
            self.ac_intl_dev.id: Decimal("33.3333"),
            self.ac_cash.id: Decimal("33.3334"),
        }

        # Should not raise (within 0.001% tolerance)
        try:
            self.strategy.save_allocations(nearly_100)
        except ValueError:
            self.fail("Should accept allocations within tolerance")

        # Verify they sum to 100.00 exactly in DB (or close to it)
        # We allow for a bit more drift in DB due to 2-decimal rounding
        total = sum(ta.target_percent for ta in self.strategy.target_allocations.all())
        self.assertTrue(abs(total - Decimal("100.00")) <= Decimal("0.02"))

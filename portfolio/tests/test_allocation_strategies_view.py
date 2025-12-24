from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import AllocationStrategy
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


class AllocationStrategyViewTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.create_portfolio(user=self.user)
        self.client.force_login(self.user)

        # Asset Classes are already set up by mixin
        self.ac1 = self.asset_class_us_equities  # US Equities
        self.ac2 = self.asset_class_intl_developed  # Intl Dev
        self.ac_cash = self.asset_class_cash

    def test_create_strategy_with_cash_remainder(self) -> None:
        """Verify cash is calculated as remainder."""
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Test Strategy",
            f"target_{self.ac1.id}": "60.00",
            f"target_{self.ac2.id}": "30.00",
            # Cash not included - should be calculated as 10%
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("portfolio:target_allocations"))

        # Verify strategy was created
        strategy = AllocationStrategy.objects.get(name="Test Strategy")

        # Verify non-cash allocations
        self.assertEqual(
            strategy.target_allocations.get(asset_class=self.ac1).target_percent, Decimal("60.00")
        )
        self.assertEqual(
            strategy.target_allocations.get(asset_class=self.ac2).target_percent, Decimal("30.00")
        )

        # Verify cash was calculated correctly
        cash_allocation = strategy.target_allocations.get(asset_class=self.ac_cash)
        self.assertEqual(cash_allocation.target_percent, Decimal("10.00"))

        # Verify total is 100%
        total = sum(ta.target_percent for ta in strategy.target_allocations.all())
        self.assertEqual(total, AllocationStrategy.TOTAL_ALLOCATION_PCT)

    def test_create_strategy_100_percent_no_cash(self) -> None:
        """Verify 100% allocation results in 0% cash."""
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "No Cash Strategy",
            f"target_{self.ac1.id}": "100.00",  # 100% equities
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("portfolio:target_allocations"))

        strategy = AllocationStrategy.objects.get(name="No Cash Strategy")

        # Cash allocation should be 0% (but record exists)
        # Note: save_allocations creates it ONLY if > 0 per logic:
        # if cash_percent > 0: create.
        # So let's check if it exists or not.

        cash_exists = strategy.target_allocations.filter(asset_class=self.ac_cash).exists()
        self.assertFalse(cash_exists, "Cash allocation should not exist if remainder is 0")

        # Verify property returns 0.00
        self.assertEqual(strategy.cash_allocation, Decimal("0.00"))

    def test_create_strategy_exceeds_100_error(self) -> None:
        """Verify validation error if > 100%."""
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Invalid Strategy",
            f"target_{self.ac1.id}": "60.00",
            f"target_{self.ac2.id}": "50.00",  # Total 110%
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)  # Re-renders form
        form = response.context["form"]
        # Form clean handles this?
        # Form clean checks total allocation > 100.
        self.assertTrue(form.errors)
        self.assertIn("Total allocation", str(form.errors))

    def test_update_strategy_recalculates_cash(self) -> None:
        """Verify updating strategy recalculates cash correctly."""
        # Initial: 60/30 -> 10 Cash
        strategy = AllocationStrategy.objects.create(user=self.user, name="Update Test Strategy")
        strategy.save_allocations({self.ac1.id: Decimal("60.00"), self.ac2.id: Decimal("30.00")})
        self.assertEqual(strategy.cash_allocation, Decimal("10.00"))

        # Update: 50/20 -> 30 Cash
        url = reverse("portfolio:strategy_update", args=[strategy.id])
        data = {
            "name": "Update Test Strategy",
            f"target_{self.ac1.id}": "50.00",
            f"target_{self.ac2.id}": "20.00",
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("portfolio:target_allocations"))

        strategy.refresh_from_db()
        self.assertEqual(
            strategy.target_allocations.get(asset_class=self.ac1).target_percent, Decimal("50.00")
        )
        self.assertEqual(strategy.cash_allocation, Decimal("30.00"))

    def test_create_strategy_with_explicit_cash(self) -> None:
        """Verify user can explicitly provide cash allocation."""
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Explicit Cash Strategy",
            f"target_{self.ac1.id}": "60.00",
            f"target_{self.ac2.id}": "30.00",
            f"target_{self.ac_cash.id}": "10.00",  # Explicit cash
        }

        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("portfolio:target_allocations"))

        strategy = AllocationStrategy.objects.get(name="Explicit Cash Strategy")

        # Verify allocations match exactly what was provided
        self.assertEqual(
            strategy.target_allocations.get(asset_class=self.ac1).target_percent, Decimal("60.00")
        )
        self.assertEqual(
            strategy.target_allocations.get(asset_class=self.ac2).target_percent, Decimal("30.00")
        )
        self.assertEqual(
            strategy.target_allocations.get(asset_class=self.ac_cash).target_percent,
            Decimal("10.00"),
        )

        # Verify total is 100%
        total = sum(ta.target_percent for ta in strategy.target_allocations.all())
        self.assertEqual(total, AllocationStrategy.TOTAL_ALLOCATION_PCT)

    def test_create_strategy_explicit_cash_wrong_sum_error(self) -> None:
        """Verify error when explicit cash doesn't sum to 100%."""
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Wrong Sum Strategy",
            f"target_{self.ac1.id}": "60.00",
            f"target_{self.ac2.id}": "30.00",
            f"target_{self.ac_cash.id}": "15.00",  # Total: 105%
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)  # Re-renders form
        form = response.context["form"]
        self.assertTrue(form.errors)
        # Should mention "100" in error message
        self.assertIn("100", str(form.errors))

    def test_create_strategy_explicit_cash_under_100_error(self) -> None:
        """Verify error when explicit cash sums to less than 100%."""
        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Under Sum Strategy",
            f"target_{self.ac1.id}": "60.00",
            f"target_{self.ac2.id}": "30.00",
            f"target_{self.ac_cash.id}": "5.00",  # Total: 95%
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)  # Re-renders form
        form = response.context["form"]
        self.assertTrue(form.errors)
        self.assertIn("100", str(form.errors))

    def test_save_allocations_direct_with_explicit_cash(self) -> None:
        """Test save_allocations() domain method with explicit cash."""
        strategy = AllocationStrategy.objects.create(user=self.user, name="Direct Test")

        # Explicit cash that sums to 100%
        strategy.save_allocations(
            {
                self.ac1.id: Decimal("60.00"),
                self.ac2.id: Decimal("30.00"),
                self.ac_cash.id: Decimal("10.00"),
            }
        )

        self.assertEqual(strategy.cash_allocation, Decimal("10.00"))
        total = sum(ta.target_percent for ta in strategy.target_allocations.all())
        self.assertEqual(total, AllocationStrategy.TOTAL_ALLOCATION_PCT)

    def test_save_allocations_direct_explicit_cash_wrong_sum(self) -> None:
        """Test save_allocations() domain method errors on wrong sum with explicit cash."""
        strategy = AllocationStrategy.objects.create(user=self.user, name="Direct Test Error")

        # Explicit cash that doesn't sum to 100%
        with self.assertRaises(ValueError) as ctx:
            strategy.save_allocations(
                {
                    self.ac1.id: Decimal("60.00"),
                    self.ac2.id: Decimal("30.00"),
                    self.ac_cash.id: Decimal("15.00"),  # Total: 105%
                }
            )

        self.assertIn("105", str(ctx.exception))
        self.assertIn("100", str(ctx.exception))

    def test_save_allocations_direct_implicit_cash(self) -> None:
        """Test save_allocations() domain method with implicit cash (existing test)."""
        strategy = AllocationStrategy.objects.create(user=self.user, name="Direct Implicit")

        # No cash provided - should auto-calculate
        strategy.save_allocations({self.ac1.id: Decimal("60.00"), self.ac2.id: Decimal("30.00")})

        self.assertEqual(strategy.cash_allocation, Decimal("10.00"))

    def test_save_allocations_direct_implicit_cash_over_100(self) -> None:
        """Test save_allocations() errors when implicit cash would be negative."""
        strategy = AllocationStrategy.objects.create(user=self.user, name="Direct Over 100")

        # No cash, but allocations exceed 100%
        with self.assertRaises(ValueError) as ctx:
            strategy.save_allocations(
                {
                    self.ac1.id: Decimal("60.00"),
                    self.ac2.id: Decimal("50.00"),  # Total: 110%
                }
            )

        self.assertIn("110", str(ctx.exception))
        self.assertIn("100", str(ctx.exception))

from decimal import Decimal
from http import HTTPStatus

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portfolio.models import AllocationStrategy, AssetClass
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


class TestAllocationStrategyCreateView(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="password")
        self.setup_portfolio_data()
        self.create_portfolio(user=self.user)

        # Create some asset classes using mixin helpers or manually
        self.ac1, _ = AssetClass.objects.get_or_create(
            name="Stocks", category=self.cat_us_eq
        )
        self.ac2, _ = AssetClass.objects.get_or_create(
            name="Bonds", category=self.cat_fi
        )

    def test_get_view_returns_200(self) -> None:
        self.client.force_login(self.user)
        url = reverse("portfolio:strategy_create")

        response = self.client.get(url)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Check template used (Django 4.x+ response.templates is list)
        self.assertIn("portfolio/allocation_strategy_form.html", [t.name for t in response.templates])
        self.assertIn("form", response.context)

        # Verify grouping headers are present
        content = response.content.decode()
        self.assertIn("US Equities", content)
        self.assertIn("Fixed Income", content)

    def test_post_creates_strategy_and_allocations(self) -> None:
        self.client.force_login(self.user)

        url = reverse("portfolio:strategy_create")
        data = {
            "name": "My Strategy",
            "description": "Balanced",
            f"target_{self.ac1.id}": "60.00",
            f"target_{self.ac2.id}": "40.00",
        }

        response = self.client.post(url, data)

        self.assertRedirects(response, reverse("portfolio:target_allocations"))

        strategy = AllocationStrategy.objects.get(name="My Strategy", user=self.user)
        self.assertEqual(strategy.description, "Balanced")

        self.assertEqual(strategy.target_allocations.count(), 2)
        t1 = strategy.target_allocations.get(asset_class=self.ac1)
        self.assertEqual(t1.target_percent, Decimal("60.00"))
        t2 = strategy.target_allocations.get(asset_class=self.ac2)
        self.assertEqual(t2.target_percent, Decimal("40.00"))

    def test_post_validation_error_over_100(self) -> None:
        self.client.force_login(self.user)

        url = reverse("portfolio:strategy_create")
        data = {
            "name": "Greedy Strategy",
            f"target_{self.ac1.id}": "60.00",
            f"target_{self.ac2.id}": "50.00",
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, HTTPStatus.OK)  # Re-renders form
        self.assertFalse(AllocationStrategy.objects.filter(name="Greedy Strategy").exists())
        self.assertContains(response, "cannot exceed 100%")

    def test_requires_login(self) -> None:
        url = reverse("portfolio:strategy_create")
        response = self.client.get(url)
        self.assertRedirects(response, f"/accounts/login/?next={url}")

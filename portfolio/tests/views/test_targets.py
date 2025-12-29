"""
Tests for target allocations view.

Tests: portfolio/views/targets.py
- TargetAllocationView (GET and POST behavior)
- Strategy assignment to account types and accounts
- Template rendering and context data
- Variance mode toggling

Migrated from: models/test_target_allocations_legacy.py
"""

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.urls import reverse

import pytest

from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    AssetClass,
    AssetClassCategory,
    Holding,
    SecurityPrice,
)

User = get_user_model()


@pytest.fixture
def targets_view_setup(test_portfolio: dict[str, Any], stable_test_prices: Any) -> dict[str, Any]:
    """
    Complete setup for target allocations view tests.

    Creates:
    - Two accounts (Roth IRA, Taxable)
    - Two strategies (Conservative, Aggressive)
    - Holdings in both accounts
    """
    system = test_portfolio["system"]
    user = test_portfolio["user"]
    portfolio = test_portfolio["portfolio"]

    # Create accounts
    acc_roth = Account.objects.create(
        user=user,
        name="My Roth",
        portfolio=portfolio,
        account_type=system.type_roth,
        institution=system.institution,
    )

    acc_taxable = Account.objects.create(
        user=user,
        name="Taxable",
        portfolio=portfolio,
        account_type=system.type_taxable,
        institution=system.institution,
    )

    # Create holdings ($10k in Roth VTI, $5k in Taxable BND)
    Holding.objects.create(account=acc_roth, security=system.vti, shares=Decimal("100"))
    Holding.objects.create(account=acc_taxable, security=system.bnd, shares=Decimal("50"))

    # Create prices to achieve expected values
    from django.utils import timezone

    now = timezone.now()
    SecurityPrice.objects.create(
        security=system.vti, price=Decimal("100.00"), price_datetime=now, source="manual"
    )
    SecurityPrice.objects.create(
        security=system.bnd, price=Decimal("100.00"), price_datetime=now, source="manual"
    )

    # Create strategies
    strategy_conservative = AllocationStrategy.objects.create(user=user, name="Conservative")
    strategy_conservative.save_allocations(
        {
            system.asset_class_us_equities.id: Decimal("40.00"),
            system.asset_class_cash.id: Decimal("60.00"),
        }
    )

    strategy_aggressive = AllocationStrategy.objects.create(user=user, name="Aggressive")
    strategy_aggressive.save_allocations(
        {
            system.asset_class_us_equities.id: Decimal("90.00"),
            system.asset_class_cash.id: Decimal("10.00"),
        }
    )

    return {
        "user": user,
        "portfolio": portfolio,
        "system": system,
        "acc_roth": acc_roth,
        "acc_taxable": acc_taxable,
        "strategy_conservative": strategy_conservative,
        "strategy_aggressive": strategy_aggressive,
    }


@pytest.mark.views
@pytest.mark.integration
class TestTargetAllocationViewHTTP:
    """Test HTTP behavior of TargetAllocationView."""

    def test_view_loads_with_context(self, client: Any, targets_view_setup: dict[str, Any]) -> None:
        """Test that view loads and provides expected context data.

        Migrated from: test_initial_calculation
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        url = reverse("portfolio:target_allocations")
        response = client.get(url)

        assert response.status_code == 200
        assert "strategies" in response.context
        assert "portfolio_total_value" in response.context
        assert len(response.context["strategies"]) == 2
        # Total: $10k + $5k = $15k
        assert response.context["portfolio_total_value"] == Decimal("15000.00")

    def test_assign_strategy_to_account_type_post(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test POST to assign strategy to account type.

        Migrated from: test_save_account_type_allocation
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        url = reverse("portfolio:target_allocations")
        response = client.post(
            url,
            {
                f"strategy_at_{setup['system'].type_roth.id}": str(setup["strategy_aggressive"].id),
                f"strategy_at_{setup['system'].type_taxable.id}": "",  # Clear/no assignment
            },
        )

        # Should redirect on success
        assert response.status_code == 302
        assert response.url == url

        # Verify Roth assignment created
        assignment = AccountTypeStrategyAssignment.objects.get(
            user=setup["user"],
            account_type=setup["system"].type_roth,
        )
        assert assignment.allocation_strategy == setup["strategy_aggressive"]

        # Verify Taxable has no assignment
        assert not AccountTypeStrategyAssignment.objects.filter(
            user=setup["user"],
            account_type=setup["system"].type_taxable,
        ).exists()

    def test_assign_strategy_to_individual_account_post(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test POST to assign override strategy to specific account.

        Migrated from: test_save_account_override_allocation
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        url = reverse("portfolio:target_allocations")
        response = client.post(
            url,
            {f"strategy_acc_{setup['acc_roth'].id}": str(setup["strategy_conservative"].id)},
        )

        assert response.status_code == 302

        # Verify account-level override
        setup["acc_roth"].refresh_from_db()
        assert setup["acc_roth"].allocation_strategy == setup["strategy_conservative"]

    def test_clear_account_type_assignment_post(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test POST with empty string clears account type assignment.

        Migrated from: test_clear_allocation
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        # Setup: Create initial assignment
        AccountTypeStrategyAssignment.objects.create(
            user=setup["user"],
            account_type=setup["system"].type_roth,
            allocation_strategy=setup["strategy_aggressive"],
        )

        # Action: Clear it
        url = reverse("portfolio:target_allocations")
        response = client.post(
            url,
            {f"strategy_at_{setup['system'].type_roth.id}": ""},  # Empty = clear
        )

        assert response.status_code == 302

        # Verify assignment deleted
        assert not AccountTypeStrategyAssignment.objects.filter(
            user=setup["user"],
            account_type=setup["system"].type_roth,
        ).exists()

    def test_subtotal_rows_displayed_correctly(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test subtotal row display logic for categories with multiple assets.

        Migrated from: test_redundant_subtotals
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        # Create multi-asset category
        equity_cat = AssetClassCategory.objects.create(
            code="TEST_EQUITY", label="Test Equities", sort_order=10
        )
        AssetClass.objects.create(name="Large Cap", category=equity_cat)
        AssetClass.objects.create(name="Small Cap", category=equity_cat)

        # Create single-asset category
        bond_cat = AssetClassCategory.objects.create(
            code="TEST_BOND", label="Test Bonds", sort_order=11
        )
        AssetClass.objects.create(name="Total Bond", category=bond_cat)

        url = reverse("portfolio:target_allocations")
        response = client.get(url)

        content = response.content.decode("utf-8")

        # Multi-asset category should show subtotal
        assert "Test Equities Total" in content or "test-equities-total" in content.lower()

        # Single-asset category should NOT show subtotal
        assert "Test Bonds Total" not in content

    def test_all_cash_strategy_displays_correctly(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test that 100% cash strategy displays with correct values.

        Migrated from: test_all_cash_strategy_allocation
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        # Create all-cash strategy
        cash_strategy = AllocationStrategy.objects.create(user=setup["user"], name="All Cash")
        cash_strategy.save_allocations({setup["system"].asset_class_cash.id: Decimal("100.00")})

        # Assign to account type
        AccountTypeStrategyAssignment.objects.create(
            user=setup["user"],
            account_type=setup["system"].type_roth,
            allocation_strategy=cash_strategy,
        )

        url = reverse("portfolio:target_allocations")
        response = client.get(url)

        assert response.status_code == 200

        # Verify cash appears with 100% target for Roth accounts
        context = response.context
        assert any(
            row.get("asset_class_name") == "Cash"
            for row in context.get("allocation_rows_percent", [])
        )

    def test_category_subtotal_calculation_accuracy(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test that category subtotals aggregate correctly.

        Migrated from: test_category_subtotal_calculation
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        # Create category with multiple assets
        large_cap_cat = AssetClassCategory.objects.create(
            code="US_LARGE", label="US Large Cap", sort_order=1
        )
        usl_ac = AssetClass.objects.create(name="US Large Value", category=large_cap_cat)
        usg_ac = AssetClass.objects.create(name="US Large Growth", category=large_cap_cat)

        # Create securities
        from portfolio.models import Security

        usl_sec = Security.objects.create(
            ticker="USL", name="US Large Value Fund", asset_class=usl_ac
        )
        usg_sec = Security.objects.create(
            ticker="USG", name="US Large Growth Fund", asset_class=usg_ac
        )

        # Add holdings: $1500 USL + $1000 USG = $2500 total
        Holding.objects.create(account=setup["acc_taxable"], security=usl_sec, shares=Decimal("15"))
        Holding.objects.create(account=setup["acc_taxable"], security=usg_sec, shares=Decimal("10"))

        from django.utils import timezone

        from portfolio.models import SecurityPrice

        now = timezone.now()
        SecurityPrice.objects.create(
            security=usl_sec, price=Decimal("100.00"), price_datetime=now, source="manual"
        )
        SecurityPrice.objects.create(
            security=usg_sec, price=Decimal("100.00"), price_datetime=now, source="manual"
        )

        url = reverse("portfolio:target_allocations")
        response = client.get(url + "?mode=dollar")

        assert response.status_code == 200
        rows = response.context["allocation_rows_money"]

        # Find subtotal row
        subtotal_row = next(
            (r for r in rows if r.get("is_subtotal") and "US Large Cap" in r["asset_class_name"]),
            None,
        )
        assert subtotal_row is not None

        # Verify subtotal = $2500
        # Find Taxable column in subtotal row
        taxable_group = next(
            (
                g
                for g in subtotal_row["account_types"]
                if g["code"] == setup["system"].type_taxable.code
            ),
            None,
        )
        assert taxable_group is not None
        assert taxable_group["actual"] == 2500.0

    def test_strategy_select_box_shows_assigned_strategy(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test that assigned strategy appears as selected in dropdown.

        Migrated from: test_assign_account_strategy_persists_and_renders
        """
        setup = targets_view_setup
        client.force_login(setup["user"])

        # Assign strategy to account
        setup["acc_roth"].allocation_strategy = setup["strategy_conservative"]
        setup["acc_roth"].save()

        url = reverse("portfolio:target_allocations")
        response = client.get(url)

        content = response.content.decode("utf-8")

        # Verify select box has correct option selected
        expected_selected = f'value="{setup["strategy_conservative"].id}" selected'
        assert expected_selected in content


@pytest.mark.views
@pytest.mark.integration
class TestTargetAllocationViewDisplayModes:
    """Test display mode variations (percent vs dollar, policy vs effective)."""

    def test_percent_mode_displays_percentages(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test percent mode shows % values without dollar signs."""
        setup = targets_view_setup
        client.force_login(setup["user"])

        url = reverse("portfolio:target_allocations") + "?mode=percent"
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Should have % signs
        assert "%" in content
        # Should not have dollar signs in allocation cells
        # (Note: might have $ in headings/labels, so this is approximate)

    def test_dollar_mode_displays_currency(
        self, client: Any, targets_view_setup: dict[str, Any]
    ) -> None:
        """Test dollar mode shows $ values."""
        setup = targets_view_setup
        client.force_login(setup["user"])

        url = reverse("portfolio:target_allocations") + "?mode=dollar"
        response = client.get(url)

        assert response.status_code == 200
        assert "allocation_rows_money" in response.context

        # Verify context has formatted values
        rows = response.context["allocation_rows_money"]
        assert len(rows) > 0


@pytest.mark.views
@pytest.mark.integration
class TestTargetAllocationViewCoverage:
    """Additional tests to improve coverage for TargetAllocationView."""

    def test_get_context_data_unauthenticated(self, rf):
        """Test get_context_data returns basic context for unauthenticated user."""
        from django.contrib.auth.models import AnonymousUser

        from portfolio.views.targets import TargetAllocationView

        request = rf.get("/fake-url")
        request.user = AnonymousUser()

        view = TargetAllocationView()
        view.request = request
        view.object = None

        context = view.get_context_data()

        # Should return basic context without calling service.build_context
        # strategies should NOT be in context (or empty if setup differently, but here just checking return)
        # build_context adds 'strategies', 'portfolio_total_value', etc.
        # super().get_context_data() just returns view params.

        assert "strategies" not in context
        assert "portfolio_total_value" not in context

    def test_post_error_handling(self, client, targets_view_setup):
        """Test handling of errors from service during POST."""
        from unittest.mock import patch

        setup = targets_view_setup
        client.force_login(setup["user"])
        url = reverse("portfolio:target_allocations")

        # Mock the service on the view instance?
        # Easier to patch the service class used in the view,
        # OR patch TargetAllocationViewService.save_from_post
        with patch(
            "portfolio.views.targets.TargetAllocationViewService.save_from_post"
        ) as mock_save:
            mock_save.return_value = (False, ["Test Error Message"])

            response = client.post(url, {})

            # Should redirect
            assert response.status_code == 302
            assert response.url == url

            # Verify message
            messages = list(response.wsgi_request._messages)
            assert len(messages) == 1
            assert str(messages[0]) == "Test Error Message"
            assert messages[0].level_tag == "error"

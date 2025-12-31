"""Integration tests for allocation engine."""

import pytest

from portfolio.services.allocations import get_sidebar_data
from portfolio.services.allocations.engine import AllocationEngine


@pytest.mark.integration
@pytest.mark.services
@pytest.mark.django_db
class TestAllocationEngineIntegration:
    """Integration tests for AllocationEngine."""

    def test_get_sidebar_data_with_holdings(self, test_user, simple_holdings):
        """Test sidebar data calculation with real data."""
        engine = AllocationEngine()
        result = engine.get_sidebar_data(test_user)

        assert "grand_total" in result
        assert "account_totals" in result
        assert "account_variances" in result
        assert "accounts_by_group" in result
        assert "query_count" in result

        # Should have some data
        assert result["grand_total"] > 0
        assert len(result["account_totals"]) > 0

    def test_get_sidebar_data_empty(self, test_user):
        """Test sidebar data with no holdings."""
        engine = AllocationEngine()
        result = engine.get_sidebar_data(test_user)

        assert result["grand_total"] == 0
        assert len(result["account_totals"]) == 0

    def test_convenience_function_sidebar(self, test_user, simple_holdings):
        """Test convenience function for sidebar data."""
        result = get_sidebar_data(test_user)

        assert "grand_total" in result
        assert result["grand_total"] > 0

    def test_get_account_totals(self, test_user, simple_holdings):
        """Test account totals calculation."""
        engine = AllocationEngine()
        totals = engine.get_account_totals(test_user)

        assert isinstance(totals, dict)
        assert len(totals) > 0

        # All values should be Decimal
        from decimal import Decimal

        for account_id, total in totals.items():
            assert isinstance(account_id, int)
            assert isinstance(total, Decimal)
            assert total >= 0

    def test_get_portfolio_total(self, test_user, simple_holdings):
        """Test portfolio total calculation."""
        engine = AllocationEngine()
        total = engine.get_portfolio_total(test_user)

        from decimal import Decimal

        assert isinstance(total, Decimal)
        assert total > 0

    def test_get_presentation_rows_complete(self, test_user, simple_holdings):
        """Test end-to-end presentation row generation."""
        engine = AllocationEngine()
        rows = engine.get_presentation_rows(test_user)

        assert len(rows) > 0

        # Verify row structure
        first_row = rows[0]
        assert "asset_class_name" in first_row
        assert "asset_class_id" in first_row
        assert "portfolio" in first_row
        assert "account_types" in first_row

        # Verify portfolio metrics are numeric
        portfolio = first_row["portfolio"]
        assert isinstance(portfolio["actual"], float)
        assert isinstance(portfolio["actual_pct"], float)
        assert isinstance(portfolio["effective_variance"], float)

        # Verify account types present
        assert len(first_row["account_types"]) > 0
        type_data = first_row["account_types"][0]
        assert "code" in type_data
        assert isinstance(type_data["actual"], float)

    def test_get_presentation_rows_empty_portfolio(self, test_user):
        """Test with no holdings."""
        engine = AllocationEngine()
        rows = engine.get_presentation_rows(test_user)

        assert rows == []


@pytest.mark.integration
@pytest.mark.services
@pytest.mark.django_db
class TestVarianceCalculations:
    """
    Test that variance calculations work correctly.

    Verifies that when actual allocations differ from target allocations,
    the variance columns show non-zero values at both:
    - Portfolio level
    - Account type level
    """

    @pytest.fixture
    def portfolio_with_targets(self, test_portfolio, roth_account):
        """
        Create portfolio with holdings that differ from targets.

        Holdings: 100% US Equities ($1000 VTI)
        Target: 60% US Equities, 40% Bonds

        This should produce 40% variance for both asset classes.
        """
        from decimal import Decimal

        from django.utils import timezone

        from portfolio.models import (
            AllocationStrategy,
            Holding,
            SecurityPrice,
            TargetAllocation,
        )

        system = test_portfolio["system"]
        user = test_portfolio["user"]

        # Create holding: 100% in US Equities ($1000 VTI)
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create strategy with different allocation: 60% US Equities, 40% Bonds
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="60/40 Strategy",
        )

        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("60.00"),
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_treasuries_short,
            target_percent=Decimal("40.00"),
        )

        # Assign strategy to the account
        roth_account.allocation_strategy = strategy
        roth_account.save()

        return {
            **test_portfolio,
            "account": roth_account,
            "strategy": strategy,
        }

    def test_portfolio_variance_is_nonzero(self, portfolio_with_targets):
        """
        Verify portfolio-level variance is calculated correctly.

        With 100% actual in US Equities vs 60% target, variance should be +40%.
        """
        user = portfolio_with_targets["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find US Equities row (not a subtotal/total row)
        us_equities_row = None
        for row in rows:
            if row.get("asset_class_name") == "US Equities":
                us_equities_row = row
                break

        assert us_equities_row is not None, (
            f"US Equities row not found. Available rows: "
            f"{[(r.get('asset_class_name'), r.get('row_type')) for r in rows]}"
        )

        portfolio = us_equities_row["portfolio"]

        # Actual should be 100%, effective should be 60%
        assert portfolio["actual_pct"] == pytest.approx(100.0, abs=0.1)
        assert portfolio["effective_pct"] == pytest.approx(60.0, abs=0.1)

        # Variance should be +40% (actual - effective)
        assert portfolio["effective_variance_pct"] == pytest.approx(40.0, abs=0.1), (
            f"Expected +40% variance, got {portfolio['effective_variance_pct']}"
        )

    def test_account_type_variance_is_nonzero(self, portfolio_with_targets):
        """
        Verify account type level variance is calculated correctly.

        The Roth IRA account type should show variance between actual
        and effective allocations.
        """
        user = portfolio_with_targets["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find US Equities row
        us_equities_row = None
        for row in rows:
            if row.get("asset_class_name") == "US Equities":
                us_equities_row = row
                break

        assert us_equities_row is not None, "US Equities row not found"

        # Should have at least one account type
        assert len(us_equities_row["account_types"]) > 0

        # Find the Roth IRA account type
        roth_type = None
        for at in us_equities_row["account_types"]:
            if "ROTH" in at["code"].upper():
                roth_type = at
                break

        assert roth_type is not None, "Roth IRA account type not found"

        # Actual should be 100%, effective should be 60%
        assert roth_type["actual_pct"] == pytest.approx(100.0, abs=0.1)
        assert roth_type["effective_pct"] == pytest.approx(60.0, abs=0.1)

        # Variance should be +40%
        assert roth_type["effective_variance_pct"] == pytest.approx(40.0, abs=0.1), (
            f"Expected +40% variance, got {roth_type['effective_variance_pct']}"
        )

    def test_subtotal_rows_have_variance(self, portfolio_with_targets):
        """
        Verify subtotal and group total rows aggregate variances correctly.

        With 100% actual in US Equities vs 60% target:
        - Equities subtotals should show +$400 variance
        - Fixed Income subtotals should show -$400 variance
        """
        user = portfolio_with_targets["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find the Equities Total (group_total) row
        equities_total = None
        fixed_income_total = None
        for row in rows:
            name = row.get("asset_class_name", "")
            if "Equities Total" in name and row.get("row_type") == "group_total":
                equities_total = row
            elif "Fixed Income Total" in name and row.get("row_type") == "subtotal":
                fixed_income_total = row

        # Equities group total should have +$400 variance (over-allocated)
        assert equities_total is not None, "Equities Total row not found"
        eq_portfolio = equities_total["portfolio"]
        assert eq_portfolio["effective_variance"] == pytest.approx(400.0, abs=1.0), (
            f"Expected Equities variance of +$400, got {eq_portfolio['effective_variance']}"
        )

        # Fixed Income subtotal should have -$400 variance (under-allocated)
        assert fixed_income_total is not None, "Fixed Income Total row not found"
        fi_portfolio = fixed_income_total["portfolio"]
        assert fi_portfolio["effective_variance"] == pytest.approx(-400.0, abs=1.0), (
            f"Expected Fixed Income variance of -$400, got {fi_portfolio['effective_variance']}"
        )

    def test_row_type_is_set_for_all_rows(self, portfolio_with_targets):
        """
        Verify all rows have a proper row_type set (not NaN).
        """
        user = portfolio_with_targets["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        for row in rows:
            row_type = row.get("row_type")
            name = row.get("asset_class_name", "???")
            assert row_type in ("asset_class", "subtotal", "group_total", "grand_total"), (
                f"Row '{name}' has invalid row_type: {row_type}"
            )

    def test_portfolio_column_has_all_template_fields(self, portfolio_with_targets):
        """
        Verify the portfolio column data structure has all fields the template expects.

        The template accesses:
        - row.portfolio.actual, row.portfolio.actual_pct
        - row.portfolio.effective, row.portfolio.effective_pct
        - row.portfolio.effective_variance, row.portfolio.effective_variance_pct
        - row.portfolio.policy_variance, row.portfolio.policy_variance_pct
        """
        user = portfolio_with_targets["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find US Equities row (should have non-zero variance)
        us_equities_row = None
        for row in rows:
            if row.get("asset_class_name") == "US Equities":
                us_equities_row = row
                break

        assert us_equities_row is not None

        portfolio = us_equities_row["portfolio"]

        # Check all fields exist
        required_fields = [
            "actual",
            "actual_pct",
            "effective",
            "effective_pct",
            "effective_variance",
            "effective_variance_pct",
            "policy_variance",
            "policy_variance_pct",
        ]

        for field in required_fields:
            assert field in portfolio, f"Missing field: {field}"
            assert isinstance(portfolio[field], float), (
                f"Field {field} is not a float: {type(portfolio[field])}"
            )

        # Verify the values are correct for US Equities
        # actual=$1000 (100%), effective=$600 (60%), variance=$400 (40%)
        assert portfolio["actual"] == pytest.approx(1000.0, abs=1.0)
        assert portfolio["actual_pct"] == pytest.approx(100.0, abs=0.1)
        assert portfolio["effective"] == pytest.approx(600.0, abs=1.0)
        assert portfolio["effective_pct"] == pytest.approx(60.0, abs=0.1)
        assert portfolio["effective_variance"] == pytest.approx(400.0, abs=1.0), (
            f"effective_variance should be 400, got {portfolio['effective_variance']}"
        )
        assert portfolio["effective_variance_pct"] == pytest.approx(40.0, abs=0.1), (
            f"effective_variance_pct should be 40, got {portfolio['effective_variance_pct']}"
        )

    def test_variance_when_no_targets_assigned(self, simple_holdings):
        """
        Verify variance is calculated correctly when no targets are assigned.

        When there are no targets:
        - effective = 0 (no weighted targets to calculate)
        - variance = actual - effective = actual - 0 = actual

        This test uses simple_holdings which has NO allocation strategy assigned.
        """
        user = simple_holdings["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find US Equities row (the only row with holdings)
        us_equities_row = None
        for row in rows:
            if row.get("asset_class_name") == "US Equities":
                us_equities_row = row
                break

        assert us_equities_row is not None, "US Equities row not found"

        portfolio = us_equities_row["portfolio"]

        # With no targets: actual=$1000, effective=$0, variance=$1000
        # Variance should equal actual when no targets are set
        assert portfolio["effective_variance"] == pytest.approx(portfolio["actual"], abs=1.0), (
            f"Expected variance to equal actual ({portfolio['actual']}), "
            f"got {portfolio['effective_variance']}"
        )


@pytest.mark.integration
@pytest.mark.services
@pytest.mark.django_db
class TestPolicyTargetCalculations:
    """
    Test that policy targets (portfolio-level strategy) work correctly.

    Policy targets come from the portfolio's allocation_strategy and represent
    what the user WANTS their allocation to be.

    Effective targets are weighted averages of account-level targets and represent
    what the user CAN ACHIEVE given their account structure.
    """

    @pytest.fixture
    def portfolio_with_different_policy_and_effective(self, test_portfolio, roth_account):
        """
        Create portfolio where policy and effective targets differ.

        Setup:
        - Account strategy: 60% US Equities, 40% Bonds (effective target)
        - Portfolio strategy: 50% US Equities, 50% Bonds (policy target)
        - Actual holdings: 100% US Equities ($1000 VTI)

        This should produce:
        - Effective variance: 100% - 60% = +40%
        - Policy variance: 100% - 50% = +50%
        """
        from decimal import Decimal

        from django.utils import timezone

        from portfolio.models import (
            AllocationStrategy,
            Holding,
            SecurityPrice,
            TargetAllocation,
        )

        system = test_portfolio["system"]
        user = test_portfolio["user"]
        portfolio_obj = test_portfolio["portfolio"]

        # Create holding: 100% in US Equities ($1000 VTI)
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("10"),
        )

        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("100"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create ACCOUNT strategy: 60% US Equities, 40% Bonds
        account_strategy = AllocationStrategy.objects.create(
            user=user,
            name="Account 60/40 Strategy",
        )
        TargetAllocation.objects.create(
            strategy=account_strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("60.00"),
        )
        TargetAllocation.objects.create(
            strategy=account_strategy,
            asset_class=system.asset_class_treasuries_short,
            target_percent=Decimal("40.00"),
        )
        roth_account.allocation_strategy = account_strategy
        roth_account.save()

        # Create PORTFOLIO strategy: 50% US Equities, 50% Bonds
        portfolio_strategy = AllocationStrategy.objects.create(
            user=user,
            name="Portfolio 50/50 Strategy",
        )
        TargetAllocation.objects.create(
            strategy=portfolio_strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("50.00"),
        )
        TargetAllocation.objects.create(
            strategy=portfolio_strategy,
            asset_class=system.asset_class_treasuries_short,
            target_percent=Decimal("50.00"),
        )
        portfolio_obj.allocation_strategy = portfolio_strategy
        portfolio_obj.save()

        return {
            **test_portfolio,
            "account": roth_account,
            "account_strategy": account_strategy,
            "portfolio_strategy": portfolio_strategy,
        }

    def test_effective_and_policy_targets_differ(
        self, portfolio_with_different_policy_and_effective
    ):
        """
        Verify effective and policy targets are calculated differently.

        With account strategy 60/40 and portfolio strategy 50/50:
        - Effective target for US Equities should be 60%
        - Policy target (explicit_target) for US Equities should be 50%
        """
        user = portfolio_with_different_policy_and_effective["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find US Equities row
        us_equities_row = None
        for row in rows:
            if row.get("asset_class_name") == "US Equities":
                us_equities_row = row
                break

        assert us_equities_row is not None, "US Equities row not found"

        portfolio = us_equities_row["portfolio"]

        # Effective target = 60% (from account strategy)
        assert portfolio["effective_pct"] == pytest.approx(60.0, abs=0.1), (
            f"Expected effective_pct=60%, got {portfolio['effective_pct']}"
        )

        # Policy target = 50% (from portfolio strategy)
        assert portfolio["explicit_target_pct"] == pytest.approx(50.0, abs=0.1), (
            f"Expected explicit_target_pct=50%, got {portfolio['explicit_target_pct']}"
        )

    def test_effective_and_policy_variances_differ(
        self, portfolio_with_different_policy_and_effective
    ):
        """
        Verify effective and policy variances are calculated correctly.

        With actual=100%, effective=60%, policy=50%:
        - Effective variance: 100% - 60% = +40%
        - Policy variance: 100% - 50% = +50%
        """
        user = portfolio_with_different_policy_and_effective["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find US Equities row
        us_equities_row = None
        for row in rows:
            if row.get("asset_class_name") == "US Equities":
                us_equities_row = row
                break

        assert us_equities_row is not None

        portfolio = us_equities_row["portfolio"]

        # Effective variance = 100% - 60% = +40%
        assert portfolio["effective_variance_pct"] == pytest.approx(40.0, abs=0.1), (
            f"Expected effective_variance_pct=40%, got {portfolio['effective_variance_pct']}"
        )

        # Policy variance = 100% - 50% = +50%
        assert portfolio["policy_variance_pct"] == pytest.approx(50.0, abs=0.1), (
            f"Expected policy_variance_pct=50%, got {portfolio['policy_variance_pct']}"
        )

    def test_toggle_would_show_different_values(
        self, portfolio_with_different_policy_and_effective
    ):
        """
        Verify the data structure supports toggling between effective and policy views.

        The template toggle should be able to switch between:
        - Effective mode: Shows effective_pct and effective_variance_pct
        - Policy mode: Shows explicit_target_pct and policy_variance_pct

        These should have different values.
        """
        user = portfolio_with_different_policy_and_effective["user"]
        engine = AllocationEngine()

        rows = engine.get_presentation_rows(user)

        # Find US Equities row
        us_equities_row = None
        for row in rows:
            if row.get("asset_class_name") == "US Equities":
                us_equities_row = row
                break

        assert us_equities_row is not None

        portfolio = us_equities_row["portfolio"]

        # Target columns should differ
        assert portfolio["effective_pct"] != portfolio["explicit_target_pct"], (
            f"effective_pct ({portfolio['effective_pct']}) should differ from "
            f"explicit_target_pct ({portfolio['explicit_target_pct']})"
        )

        # Variance columns should differ
        assert portfolio["effective_variance_pct"] != portfolio["policy_variance_pct"], (
            f"effective_variance_pct ({portfolio['effective_variance_pct']}) should differ from "
            f"policy_variance_pct ({portfolio['policy_variance_pct']})"
        )

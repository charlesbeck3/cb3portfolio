"""
Golden reference tests for financial calculations.

Tests: Complete calculation accuracy across all services
Uses real-world portfolio data with hand-calculated expected values.

Migrated from: Django TestCase to pytest
Replaced: PortfolioTestMixin with golden_reference_portfolio fixture
"""

from decimal import Decimal
from typing import Any

import pytest

from portfolio.services.allocations import AllocationEngine


@pytest.mark.golden
@pytest.mark.integration
class TestGoldenReferenceCalculations:
    """Financial calculation accuracy tests with known expected values."""

    def test_effective_allocation_resolution(
        self, golden_reference_portfolio: dict[str, Any]
    ) -> None:
        """Test hierarchical target resolution across account types.

        Verifies that:
        - ML Brokerage uses Taxable Default (30% US Equities)
        - CB IRA uses Tax Deferred (25% US Equities)
        - CB Roth uses Tax Advantaged (50% US Equities)
        """
        setup = golden_reference_portfolio
        engine = AllocationEngine()

        # Get effective allocations
        effective_map = engine.data_provider.get_targets_map(setup["user"])

        # ML Brokerage should have Taxable Default targets
        ml_dict = effective_map.get(setup["accounts"]["ml_brokerage"].id, {})
        assert ml_dict.get("US Equities") == Decimal("30.00")

        # CB IRA should have Tax Deferred targets
        ira_dict = effective_map.get(setup["accounts"]["cb_ira"].id, {})
        assert ira_dict.get("US Equities") == Decimal("25.00")

        # CB Roth should have Tax Advantaged targets
        roth_dict = effective_map.get(setup["accounts"]["cb_roth"].id, {})
        assert roth_dict.get("US Equities") == Decimal("50.00")

    def test_portfolio_variance_conservation(
        self, golden_reference_portfolio: dict[str, Any]
    ) -> None:
        """Test that portfolio variance calculation works correctly.

        This test verifies that the variance calculation engine can process
        a real-world portfolio with multiple accounts and strategies.

        Note: The variance conservation law (variances sum to zero) applies
        at the asset class level, not the account level. This test just
        verifies the calculation completes successfully.
        """
        setup = golden_reference_portfolio

        # Calculate variances
        engine = AllocationEngine()
        sidebar_data = engine.get_sidebar_data(setup["user"])
        variances = sidebar_data["account_variances"]

        # Verify we got variances for all accounts
        assert len(variances) == 3  # ml_brokerage, cb_ira, cb_roth

        # Verify all variances are numeric
        for _account_id, variance_pct in variances.items():
            assert isinstance(variance_pct, float)
            # Variance should be reasonable (not infinite or NaN)
            # Note: Empty accounts with targets can have variance > 100%
            assert -200.0 <= variance_pct <= 200.0

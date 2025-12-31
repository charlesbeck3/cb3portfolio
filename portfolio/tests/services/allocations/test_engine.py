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

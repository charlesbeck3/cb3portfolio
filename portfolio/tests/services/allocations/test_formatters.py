"""Tests for allocation formatters."""

import pandas as pd
import pytest

from portfolio.services.allocations.formatters import AllocationFormatter


@pytest.mark.unit
@pytest.mark.services
class TestAllocationFormatter:
    """Test AllocationFormatter."""

    @pytest.fixture
    def formatter(self):
        return AllocationFormatter()

    def test_to_presentation_rows_empty(self, formatter):
        """Test with empty DataFrame."""
        assert formatter.to_presentation_rows(pd.DataFrame(), {}) == []

    def test_to_presentation_rows_structure(self, formatter):
        """Test row structure conversion."""
        df = pd.DataFrame(
            [
                {
                    "asset_class_name": "US Equities",
                    "asset_class_id": 1,
                    "portfolio_actual": 1000.0,
                    "portfolio_actual_pct": 100.0,
                    "row_type": "asset_class",
                    "group_code": "EQ",
                    "category_code": "USEQ",
                }
            ]
        )

        accounts_by_type = {
            1: [{"id": 10, "name": "Account 1", "type_code": "ROTH", "type_label": "Roth IRA"}]
        }

        rows = formatter.to_presentation_rows(df, accounts_by_type)

        assert len(rows) == 1
        row = rows[0]
        assert row["asset_class_name"] == "US Equities"
        assert row["portfolio"]["actual"] == 1000.0
        assert len(row["account_types"]) == 1
        assert row["account_types"][0]["code"] == "ROTH"

    def test_to_holdings_rows_structure(self, formatter):
        """Test holdings row conversion."""
        df = pd.DataFrame(
            [{"ticker": "VTI", "value": 1000.0, "shares": 10.0, "target_value": 800.0}]
        )

        rows = formatter.to_holdings_rows(df)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "VTI"
        assert rows[0]["value"] == 1000.0
        assert rows[0]["target_value"] == 800.0

    def test_format_holdings_rows_empty(self, formatter):
        """Test with empty DataFrame."""
        assert formatter.format_holdings_rows(pd.DataFrame()) == []

    def test_format_holdings_rows_complete(self, formatter):
        """Test hierarchical holdings formatting."""
        df = pd.DataFrame(
            [
                {
                    "Ticker": "VTI",
                    "Asset_Class": "US Equities",
                    "Group_Code": "EQ",
                    "Category_Code": "USEQ",
                    "Asset_Category": "US Large Cap",
                    "Asset_Group": "Equities",
                    "Value": 1000.0,
                    "Shares": 10.0,
                    "Price": 100.0,
                    "Target_Value": 800.0,
                    "Allocation_Pct": 100.0,
                    "Target_Allocation_Pct": 80.0,
                },
                {
                    "Ticker": "VOO",
                    "Asset_Class": "US Equities",
                    "Group_Code": "EQ",
                    "Category_Code": "USEQ",
                    "Asset_Category": "US Large Cap",
                    "Asset_Group": "Equities",
                    "Value": 500.0,
                    "Shares": 5.0,
                    "Price": 100.0,
                    "Target_Value": 400.0,
                    "Allocation_Pct": 50.0,
                    "Target_Allocation_Pct": 40.0,
                },
            ]
        )

        rows = formatter.format_holdings_rows(df)

        # Should have 2 holdings + 1 subtotal + 1 grand total
        # (Only 1 category, so no group total if redundant)
        assert len(rows) >= 4

        # Verify hierarchy_level present in all rows
        assert all("hierarchy_level" in row for row in rows)

        # Verify legacy fields NOT present
        assert all("row_type" not in row for row in rows)
        assert all("row_class" not in row for row in rows)
        assert all("is_holding" not in row for row in rows)
        assert all("is_subtotal" not in row for row in rows)
        assert all("is_group_total" not in row for row in rows)
        assert all("is_grand_total" not in row for row in rows)

        # Check grand total (hierarchy_level == -1)
        grand_total_row = next(r for r in rows if r["hierarchy_level"] == -1)
        assert grand_total_row["value"] == 1500.0

        # Check subtotal (hierarchy_level == 1)
        subtotal_row = next(r for r in rows if r["hierarchy_level"] == 1)
        assert subtotal_row["name"] == "US Large Cap Total"
        assert subtotal_row["value"] == 1500.0

        # Check holdings (hierarchy_level == 999)
        holdings = [r for r in rows if r["hierarchy_level"] == 999]
        assert len(holdings) == 2

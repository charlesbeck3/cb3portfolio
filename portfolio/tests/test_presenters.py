from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from portfolio.presenters.holdings import HoldingsTableBuilder


class HoldingsTableBuilderTests(TestCase):
    def test_build_rows_flattens_structure_and_calculates_variances(self) -> None:
        # Mock Data Structure simulating SummaryService output
        # Hierarchy: Group -> Categories -> Holdings

        # Holding Mock
        holding_1 = MagicMock()
        holding_1.ticker = "AAPL"
        holding_1.name = "Apple Inc."
        holding_1.asset_class = "US Stocks"
        holding_1.category_code = "US_STOCKS"
        holding_1.current_price = Decimal("150.00")
        holding_1.shares = Decimal("10.00")
        holding_1.target_shares = Decimal("12.00")  # Variance: -2 shares
        holding_1.value = Decimal("1500.00")
        holding_1.target_value = Decimal("2000.00") # Variance: -500 value
        # Portfolio Total is 5000.
        # Alloc: 1500/5000 = 30%. Target Alloc: 2000/5000 = 40%. Var: -10%

        holding_2 = MagicMock()
        holding_2.ticker = "GOOGL"
        holding_2.name = "Alphabet Inc."
        holding_2.asset_class = "US Stocks"
        holding_2.category_code = "US_STOCKS"
        holding_2.current_price = Decimal("2800.00")
        holding_2.shares = Decimal("1.00")
        holding_2.target_shares = Decimal("1.00")
        holding_2.value = Decimal("2800.00")
        holding_2.target_value = Decimal("2500.00")

        # Category Mock
        cat_data = MagicMock()
        cat_data.label = "US Stocks"
        cat_data.holdings = [holding_1, holding_2]
        cat_data.total = Decimal("4300.00")  # 1500 + 2800
        cat_data.total_target_value = Decimal("4500.00") # 2000 + 2500

        # Group Mock
        group_data = MagicMock()
        group_data.label = "Equity"
        group_data.categories = {"US_STOCKS": cat_data}
        group_data.total = Decimal("4300.00")
        group_data.total_target_value = Decimal("4500.00")

        holding_groups = {"EQUITY": group_data}

        grand_total_data = {
            "total": Decimal("5000.00"),  # Assume some cash elsewhere making up the diff?
            # 4300 equity + 700 cash
            "target": Decimal("5000.00"),
        }

        builder = HoldingsTableBuilder()
        rows = builder.build_rows(holding_groups, grand_total_data)

        # Assertions
        # Row 0: Holding AAPL
        self.assertEqual(rows[0].ticker, "AAPL")
        self.assertEqual(rows[0].shares_variance_raw, Decimal("-2.00"))
        self.assertEqual(rows[0].value_variance_raw, Decimal("-500.00"))
        # Alloc: 30% - 40% = -10%
        self.assertEqual(rows[0].allocation, "30.00%")
        self.assertEqual(rows[0].target_allocation, "40.00%")
        self.assertEqual(rows[0].allocation_variance, "(10.00%)")

        # Row 1: Holding GOOGL
        self.assertEqual(rows[1].ticker, "GOOGL")

        # Row 2: Category Subtotal (omitted if only 1 category? No, check builder logic)
        # Builder: if len(group_data.categories) > 1 -> Subtotal.
        # Here we only have 1 category. So NO subtotal row.

        # Row 2: Group Total
        self.assertEqual(rows[2].is_group_total, True)
        self.assertEqual(rows[2].name, "Equity Total")
        self.assertEqual(rows[2].value_raw, Decimal("4300.00"))

        # Row 3: Grand Total
        self.assertEqual(rows[3].is_grand_total, True)
        self.assertEqual(rows[3].value_raw, Decimal("5000.00"))
        self.assertEqual(rows[3].allocation, "100.00%")

    def test_rendering_subtotals_for_multiple_categories(self) -> None:
        # Mock Data with 2 categories
        cat1 = MagicMock()
        cat1.label = "Cat1"
        cat1.holdings = []
        cat1.total = Decimal("100")
        cat1.total_target_value = Decimal("100")

        cat2 = MagicMock()
        cat2.label = "Cat2"
        cat2.holdings = []
        cat2.total = Decimal("200")
        cat2.total_target_value = Decimal("200")

        group_data = MagicMock()
        group_data.label = "Group"
        group_data.categories = {"C1": cat1, "C2": cat2}
        group_data.total = Decimal("300")
        group_data.total_target_value = Decimal("300")

        holding_groups = {"G": group_data}
        grand_total_data = {"total": Decimal("300"), "target": Decimal("300")}

        builder = HoldingsTableBuilder()
        rows = builder.build_rows(holding_groups, grand_total_data)

        # Structure:
        # Cat1 Holdings (0)
        # Cat1 Subtotal
        # Cat2 Holdings (0)
        # Cat2 Subtotal
        # Group Total
        # Grand Total

        # Find subtotal rows
        subtotals = [r for r in rows if r.is_subtotal]
        self.assertEqual(len(subtotals), 2)
        self.assertEqual(subtotals[0].name, "Cat1 Total")
        self.assertEqual(subtotals[1].name, "Cat2 Total")

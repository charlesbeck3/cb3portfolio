from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import (
    Account,
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Institution,
    Portfolio,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.services.allocation_presentation import AllocationPresentationFormatter

User = get_user_model()

class TestAllocationVectorized(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser")
        self.engine = AllocationCalculationEngine()
        self.formatter = AllocationPresentationFormatter()

        # Create basic metadata
        self.parent_cat = AssetClassCategory.objects.create(code="EQ", label="Equities")
        self.category = AssetClassCategory.objects.create(code="US", label="US Stock", parent=self.parent_cat)
        self.ac = AssetClass.objects.create(name="Large Cap", category=self.category)

        self.portfolio = Portfolio.objects.create(user=self.user, name="Main")
        self.institution = Institution.objects.create(name="Vanguard")
        self.ac_group = AccountGroup.objects.create(name="Investments", sort_order=1)
        self.ac_type = AccountType.objects.create(label="Taxable", code="TAX", group=self.ac_group)
        self.account = Account.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            name="Brokerage",
            account_type=self.ac_type,
            institution=self.institution
        )

    def test_build_presentation_dataframe_structure(self) -> None:
        """Verify the structure of the refactored presentation dataframe."""
        # Create some holdings
        from portfolio.models import Holding, Security
        ticker = Security.objects.create(ticker="VT", name="Vanguard Total", asset_class=self.ac)
        Holding.objects.create(account=self.account, security=ticker, shares=Decimal("10"), current_price=Decimal("100.00"))

        df = self.engine.build_presentation_dataframe(self.user)

        # Verify MultiIndex
        self.assertEqual(df.index.names, ["group_code", "category_code", "asset_class_name"])

        # Verify columns
        self.assertIn("portfolio_current", df.columns)
        self.assertIn("portfolio_target", df.columns)
        self.assertIn("TAX_current", df.columns)
        self.assertIn("TAX_Brokerage_current", df.columns)

    def test_aggregation_vectorized(self) -> None:
        """Verify that aggregate_presentation_levels returns correct structure."""
        # Create some holdings
        from portfolio.models import Holding, Security
        ticker = Security.objects.create(ticker="VT", name="Vanguard Total", asset_class=self.ac)
        Holding.objects.create(account=self.account, security=ticker, shares=Decimal("10"), current_price=Decimal("100.00"))

        df = self.engine.build_presentation_dataframe(self.user)
        aggregated = self.engine.aggregate_presentation_levels(df)

        self.assertIn("assets", aggregated)
        self.assertIn("category_subtotals", aggregated)
        self.assertIn("group_totals", aggregated)
        self.assertIn("grand_total", aggregated)

    def test_formatting_vectorized(self) -> None:
        """Verify presentation formatter output."""
        from portfolio.models import Holding, Security
        ticker = Security.objects.create(ticker="VT", name="Vanguard Total", asset_class=self.ac)
        Holding.objects.create(account=self.account, security=ticker, shares=Decimal("10"), current_price=Decimal("100.00"))

        df = self.engine.build_presentation_dataframe(self.user)
        aggregated = self.engine.aggregate_presentation_levels(df)

        ac_meta, _ = self.engine._get_asset_class_metadata(self.user)
        _, accounts_by_type = self.engine._get_account_metadata(self.user)
        target_strategies = self.engine._get_target_strategies(self.user)

        rows = self.formatter.format_presentation_rows(
            aggregated, accounts_by_type, target_strategies, mode="percent"
        )

        self.assertTrue(len(rows) > 0)
        first_row = rows[0]
        self.assertIn("portfolio", first_row)
        self.assertIn("current", first_row["portfolio"])
        self.assertTrue(str(first_row["portfolio"]["current"]).endswith("%"))

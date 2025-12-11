from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolio.models import (
    Account,
    AccountGroup,
    AccountType,
    AssetCategory,
    AssetClass,
    Holding,
    Institution,
    Security,
    TargetAllocation,
)
from portfolio.services import PortfolioSummaryService

from ..base import PortfolioTestMixin

User = get_user_model()


class PortfolioSummaryServiceTests(TestCase, PortfolioTestMixin):
    def setUp(self) -> None:
        self.setup_portfolio_data()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.institution = Institution.objects.create(name="Vanguard")

        # Create Assets
        # Use categories from mixin: self.cat_us_eq, self.cat_fi
        self.asset_class_us = AssetClass.objects.create(name="US Stocks", category=self.cat_us_eq)
        self.asset_class_bonds = AssetClass.objects.create(name="Bonds", category=self.cat_fi)

        # Create Account using AccountType object
        self.account_roth = Account.objects.create(
            user=self.user,
            name="Roth IRA",
            account_type=self.type_roth,
            institution=self.institution,
        )
        self.account_taxable = Account.objects.create(
            user=self.user,
            name="Taxable",
            account_type=self.type_taxable,
            institution=self.institution,
        )

        # Create Securities
        self.sec_vti = Security.objects.create(
            ticker="VTI", name="Vanguard Total Stock Market", asset_class=self.asset_class_us
        )
        self.sec_bnd = Security.objects.create(
            ticker="BND", name="Vanguard Total Bond Market", asset_class=self.asset_class_bonds
        )

        # Create Holdings
        self.holding_vti_roth = Holding.objects.create(
            account=self.account_roth,
            security=self.sec_vti,
            shares=Decimal("10.0"),
            current_price=Decimal("200.00"),
        )
        self.holding_bnd_taxable = Holding.objects.create(
            account=self.account_taxable,
            security=self.sec_bnd,
            shares=Decimal("20.0"),
            current_price=Decimal("80.00"),
        )

    @patch("portfolio.services.MarketDataService.get_prices")
    def test_update_prices(self, mock_get_prices: MagicMock) -> None:
        """Test the orchestration logic: fetch holdings -> get prices -> update DB."""
        mock_get_prices.return_value = {"VTI": Decimal("210.00"), "BND": Decimal("85.00")}

        PortfolioSummaryService.update_prices(self.user)

        # Verify MarketDataService was called with correct tickers
        # Order doesn't matter for set, but list order might vary.
        # Check that the call argument contains 'VTI' and 'BND' and length is 2.
        self.assertTrue(mock_get_prices.called)
        called_tickers = mock_get_prices.call_args[0][0]
        self.assertEqual(len(called_tickers), 2)
        self.assertIn("VTI", called_tickers)
        self.assertIn("BND", called_tickers)

        # Verify DB Updates
        self.holding_vti_roth.refresh_from_db()
        self.holding_bnd_taxable.refresh_from_db()

        self.assertEqual(self.holding_vti_roth.current_price, Decimal("210.00"))
        self.assertEqual(self.holding_bnd_taxable.current_price, Decimal("85.00"))

    @patch("portfolio.services.PortfolioSummaryService.update_prices")
    def test_get_holdings_summary(self, mock_update_prices: MagicMock) -> None:
        # Ensure prices are set (already set in setUp, but update_prices is mocked so they won't change)
        summary = PortfolioSummaryService.get_holdings_summary(self.user)
        # VTI in Roth: 10 * 200 = 2000
        # BND in Taxable: 20 * 80 = 1600
        # Check Grand Total
        self.assertEqual(summary.grand_total, Decimal("3600.00"))
        # Check Account Type Grand Totals
        self.assertEqual(summary.account_type_grand_totals["ROTH_IRA"], Decimal("2000.00"))
        self.assertEqual(summary.account_type_grand_totals["TAXABLE"], Decimal("1600.00"))
        # Check Categories
        equities = summary.categories["US_EQUITIES"]
        self.assertEqual(equities.total, Decimal("2000.00"))
        equities_us = equities.asset_classes["US Stocks"]
        self.assertEqual(equities_us.total, Decimal("2000.00"))
        self.assertEqual(equities_us.account_types["ROTH_IRA"].current, Decimal("2000.00"))
        fixed_income = summary.categories["FIXED_INCOME"]
        self.assertEqual(fixed_income.total, Decimal("1600.00"))
        fixed_income_bonds = fixed_income.asset_classes["Bonds"]
        self.assertEqual(fixed_income_bonds.total, Decimal("1600.00"))
        self.assertEqual(fixed_income_bonds.account_types["TAXABLE"].current, Decimal("1600.00"))
        equities_group = summary.groups["EQUITIES"]
        self.assertEqual(equities_group.label, "Equities")
        self.assertEqual(equities_group.total, Decimal("2000.00"))
        self.assertIn("US_EQUITIES", equities_group.categories)
        self.assertEqual(equities_group.total, Decimal("2000.00"))
        self.assertIn("US_EQUITIES", equities_group.categories)

        # Check account type percentage share of grand total (rounded to 2 decimal places)
        percentages = summary.account_type_percentages
        self.assertEqual(percentages["ROTH_IRA"].quantize(Decimal("0.01")), Decimal("55.56"))
        self.assertEqual(percentages["TAXABLE"].quantize(Decimal("0.01")), Decimal("44.44"))

    @patch("portfolio.services.PortfolioSummaryService.update_prices")
    def test_get_holdings_summary_with_targets_and_variance(
        self, mock_update_prices: MagicMock
    ) -> None:
        """Target allocations should produce target dollar amounts and zero variance when aligned."""

        # Set simple 100% targets for each account type and asset class
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class_us,
            target_pct=Decimal("100.0"),
        )
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_taxable,
            asset_class=self.asset_class_bonds,
            target_pct=Decimal("100.0"),
        )

        summary = PortfolioSummaryService.get_holdings_summary(self.user)

        # Grand totals
        self.assertEqual(summary.grand_total, Decimal("3600.00"))
        self.assertEqual(summary.grand_target_total, Decimal("3600.00"))
        self.assertEqual(summary.grand_variance_total, Decimal("0.00"))

        # Account-type level target and variance totals
        self.assertEqual(summary.account_type_grand_target_totals["ROTH_IRA"], Decimal("2000.00"))
        self.assertEqual(summary.account_type_grand_target_totals["TAXABLE"], Decimal("1600.00"))
        self.assertEqual(summary.account_type_grand_variance_totals["ROTH_IRA"], Decimal("0.00"))
        self.assertEqual(summary.account_type_grand_variance_totals["TAXABLE"], Decimal("0.00"))

        # Category-level rollups
        equities = summary.categories["US_EQUITIES"]
        equities_targets = equities.account_type_target_totals
        equities_variances = equities.account_type_variance_totals
        self.assertEqual(equities_targets["ROTH_IRA"], Decimal("2000.00"))
        self.assertEqual(equities_variances["ROTH_IRA"], Decimal("0.00"))

        fixed_income = summary.categories["FIXED_INCOME"]
        fixed_income_targets = fixed_income.account_type_target_totals
        fixed_income_variances = fixed_income.account_type_variance_totals
        self.assertEqual(fixed_income_targets["TAXABLE"], Decimal("1600.00"))
        self.assertEqual(fixed_income_variances["TAXABLE"], Decimal("0.00"))

        # Asset-class level target and variance
        equities_us = equities.asset_classes["US Stocks"]
        roth_data = equities_us.account_types["ROTH_IRA"]
        self.assertEqual(roth_data.current, Decimal("2000.00"))
        self.assertEqual(roth_data.target, Decimal("2000.00"))
        self.assertEqual(roth_data.variance, Decimal("0.00"))

        fixed_income_bonds = fixed_income.asset_classes["Bonds"]
        taxable_data = fixed_income_bonds.account_types["TAXABLE"]
        self.assertEqual(taxable_data.current, Decimal("1600.00"))
        self.assertEqual(taxable_data.target, Decimal("1600.00"))
        self.assertEqual(taxable_data.variance, Decimal("0.00"))

    @patch("portfolio.services.PortfolioSummaryService.update_prices")
    def test_get_account_summary(self, mock_update_prices: MagicMock) -> None:
        summary = PortfolioSummaryService.get_account_summary(self.user)

        # Check grand total
        self.assertEqual(summary["grand_total"], Decimal("3600.00"))

        # Check groups
        groups = summary["groups"]
        self.assertIn("Retirement", groups)
        self.assertIn("Investments", groups)

        retirement = groups["Retirement"]
        self.assertEqual(retirement["total"], Decimal("2000.00"))
        self.assertEqual(len(retirement["accounts"]), 1)
        self.assertEqual(retirement["accounts"][0]["name"], "Roth IRA")

        investments = groups["Investments"]
        self.assertEqual(investments["total"], Decimal("1600.00"))
        self.assertEqual(len(investments["accounts"]), 1)
        self.assertEqual(investments["accounts"][0]["name"], "Taxable")

    @patch("portfolio.services.PortfolioSummaryService.update_prices")
    def test_get_holdings_by_category(self, mock_update_prices: MagicMock) -> None:
        result = PortfolioSummaryService.get_holdings_by_category(self.user)

        grand_total = result["grand_total"]
        self.assertEqual(grand_total, Decimal("3600.00"))

        holding_groups = result["holding_groups"]

        # Check Equities Group
        self.assertIn("EQUITIES", holding_groups)
        equities_group = holding_groups["EQUITIES"]
        self.assertEqual(equities_group.label, "Equities")
        self.assertEqual(equities_group.total, Decimal("2000.00"))

        # Check US Equities Category within Equities Group
        self.assertIn("US_EQUITIES", equities_group.categories)
        us_equities = equities_group.categories["US_EQUITIES"]
        self.assertEqual(us_equities.label, "US Equities")
        self.assertEqual(us_equities.total, Decimal("2000.00"))
        self.assertEqual(len(us_equities.holdings), 1)

        vti_holding = us_equities.holdings[0]
        self.assertEqual(vti_holding.ticker, "VTI")
        self.assertEqual(vti_holding.value, Decimal("2000.00"))

        # Check Fixed Income Group
        self.assertIn("FIXED_INCOME", holding_groups)
        fixed_income_group = holding_groups["FIXED_INCOME"]
        self.assertEqual(fixed_income_group.label, "Fixed Income")
        self.assertEqual(fixed_income_group.total, Decimal("1600.00"))

        # Check Fixed Income Category
        self.assertIn("FIXED_INCOME", fixed_income_group.categories)
        fi_category = fixed_income_group.categories["FIXED_INCOME"]
        self.assertEqual(fi_category.total, Decimal("1600.00"))
        self.assertEqual(len(fi_category.holdings), 1)

        bnd_holding = fi_category.holdings[0]
        self.assertEqual(bnd_holding.ticker, "BND")
        self.assertEqual(bnd_holding.value, Decimal("1600.00"))

    @patch("portfolio.services.PortfolioSummaryService.update_prices")
    def test_get_account_summary_sorting(self, mock_update_prices: MagicMock) -> None:
        # Create a third account type with a middle value to verify sorting
        # Roth: 2000 (Retirement)
        # Taxable: 1600 (Investments)
        # Let's add a Cash account with 3000 (Cash) to be the top

        # Note: The service uses a hardcoded map for account types to groups.
        # 'ROTH_IRA' -> 'Retirement'
        # 'TAXABLE' -> 'Investments'
        # We need to ensure we can map to 'Cash' or just use the existing groups with different totals.
        # The service defaults to 'Investments' if not found in map, but we want to test sorting of groups.
        # Let's just manipulate the existing accounts to change totals.

        # Make Taxable (Investments) the largest
        self.holding_bnd_taxable.shares = Decimal("100.0")  # 100 * 80 = 8000
        self.holding_bnd_taxable.save()

        # Roth (Retirement) is 2000

        summary = PortfolioSummaryService.get_account_summary(self.user)
        groups = list(summary["groups"].keys())

        # Expect Investments (8000) then Retirement (2000)
        self.assertEqual(groups, ["Investments", "Retirement"])

        # Now make Roth (Retirement) the largest
        self.holding_vti_roth.shares = Decimal("100.0")  # 100 * 200 = 20000
        self.holding_vti_roth.save()

        summary = PortfolioSummaryService.get_account_summary(self.user)
        groups = list(summary["groups"].keys())

        # Expect Retirement (20000) then Investments (8000)
        self.assertEqual(groups, ["Retirement", "Investments"])

    @patch("portfolio.services.PortfolioSummaryService.update_prices")
    def test_get_account_summary_absolute_deviation(self, mock_update_prices: MagicMock) -> None:
        """Test absolute deviation calculation."""
        # Setup specific scenario for Roth Account
        # Total Value: $100
        # US Stock: $60 (Target 50% -> $50) -> Dev 10
        # Bonds: $40 (Target 50% -> $50) -> Dev 10
        # Total Dev: 20

        # Modify existing holding (US Stocks)
        self.holding_vti_roth.current_price = Decimal("1.00")
        self.holding_vti_roth.shares = Decimal("60.00")
        self.holding_vti_roth.save()

        # Add new holding (Bonds) to same account
        Holding.objects.create(
            account=self.account_roth,
            security=self.sec_bnd,
            shares=Decimal("40.00"),
            current_price=Decimal("1.00"),
        )

        # Create Targets
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class_us,
            target_pct=Decimal("50.0"),
        )
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.type_roth,
            asset_class=self.asset_class_bonds,
            target_pct=Decimal("50.0"),
        )

        summary = PortfolioSummaryService.get_account_summary(self.user)

        # Find Roth account
        roth_account = None
        for group in summary["groups"].values():
            for acc in group["accounts"]:
                if acc["name"] == "Roth IRA":
                    roth_account = acc
                    break

        self.assertIsNotNone(roth_account)
        assert roth_account is not None
        self.assertEqual(roth_account["total"], Decimal("100.00"))
        self.assertEqual(roth_account["absolute_deviation"], Decimal("20.00"))
        self.assertEqual(roth_account["absolute_deviation_pct"], Decimal("20.00"))


class VTargetSubtotalTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="wt_user", password="password")
        self.institution = Institution.objects.create(name="Test Bank")

        # Categories and groups mirroring US Equities
        self.cat_us_eq, _ = AssetCategory.objects.get_or_create(
            code="US_EQUITIES", label="US Equities"
        )

        # Simple account type and account (WF S&P analogue)
        self.group_equities = AccountGroup.objects.create(name="Equities", sort_order=1)
        self.at_taxable = AccountType.objects.create(
            code="WF_SAP_TYPE",
            label="WF S&P Type",
            group=self.group_equities,
            tax_treatment="TAXABLE",
        )

        self.account_wf = Account.objects.create(
            user=self.user,
            name="WF S&P",
            account_type=self.at_taxable,
            institution=self.institution,
        )

        # Asset class: US Equities
        self.ac_us_equities = AssetClass.objects.create(name="US Equities", category=self.cat_us_eq)

        # Security and holding: 69,983 current value
        self.sec_us = Security.objects.create(
            ticker="USEQ",
            name="US Equities Fund",
            asset_class=self.ac_us_equities,
        )

        Holding.objects.create(
            account=self.account_wf,
            security=self.sec_us,
            shares=Decimal("69983.00"),
            current_price=Decimal("1.00"),
        )

        # Override target: 100% US Equities for this account
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.at_taxable,
            account=self.account_wf,
            asset_class=self.ac_us_equities,
            target_pct=Decimal("100.00"),
        )

    def test_us_equities_category_vtarget_is_current_minus_target(self) -> None:
        """For an account fully invested in its override target, vTarget dollars should be zero at both row and category subtotal level."""

        summary = PortfolioSummaryService.get_holdings_summary(self.user)

        # Locate US Equities category and asset class
        us_cat = summary.categories["US_EQUITIES"]
        ac_entry = us_cat.asset_classes["US Equities"]

        # Current and target dollars at asset-class level for this account type
        at_code = self.at_taxable.code
        at_data = ac_entry.account_types[at_code]

        self.assertEqual(at_data.current, Decimal("69983.00"))
        self.assertEqual(at_data.target, Decimal("69983.00"))
        self.assertEqual(at_data.variance, Decimal("0.00"))

        # Per-account target dollars via account_asset_targets map
        ac_id = ac_entry.id
        assert ac_id is not None
        acct_targets_for_account = summary.account_asset_targets[self.account_wf.id]
        self.assertEqual(acct_targets_for_account[ac_id], Decimal("69983.00"))

        # Category-level per-account totals should be consistent
        cat_curr = us_cat.account_totals[self.account_wf.id]
        cat_target = us_cat.account_target_totals[self.account_wf.id]
        self.assertEqual(cat_curr, Decimal("69983.00"))
        self.assertEqual(cat_target, Decimal("69983.00"))
        self.assertEqual(cat_curr - cat_target, Decimal("0.00"))

        # And pre-calculated category variance for this account should match the same subtraction
        self.assertEqual(
            us_cat.account_variance_totals[self.account_wf.id],
            cat_curr - cat_target,
        )


class CashVTargetTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="cash_test_user", password="password")
        self.institution = Institution.objects.create(name="Test Bank")

        # Cash category
        self.cat_cash, _ = AssetCategory.objects.get_or_create(code="CASH", label="Cash")

        # Account type and account (WF Cash analogue)
        self.group_cash = AccountGroup.objects.create(name="Cash", sort_order=1)
        self.at_cash = AccountType.objects.create(
            code="WF_CASH_TYPE",
            label="WF Cash Type",
            group=self.group_cash,
            tax_treatment="TAXABLE",
        )

        self.account_wf_cash = Account.objects.create(
            user=self.user,
            name="WF Cash Account",
            account_type=self.at_cash,
            institution=self.institution,
        )

        # Cash asset class
        self.ac_cash = AssetClass.objects.create(name="Cash", category=self.cat_cash)

        # Security and holding: $50,000 cash equivalent
        self.sec_cash = Security.objects.create(
            ticker="CASH",
            name="Cash Fund",
            asset_class=self.ac_cash,
        )

        Holding.objects.create(
            account=self.account_wf_cash,
            security=self.sec_cash,
            shares=Decimal("50000.00"),
            current_price=Decimal("1.00"),
        )

        # Override target: 100% Cash for this account
        TargetAllocation.objects.create(
            user=self.user,
            account_type=self.at_cash,
            account=self.account_wf_cash,
            asset_class=self.ac_cash,
            target_pct=Decimal("100.00"),
        )

    def test_cash_vtarget_is_current_minus_target(self) -> None:
        """For a cash account with 100% allocation, vTarget should be 0% when current and target are both 100%."""

        summary = PortfolioSummaryService.get_holdings_summary(self.user)

        # Locate Cash asset class
        cash_cat = summary.categories["CASH"]
        cash_ac_entry = cash_cat.asset_classes["Cash"]

        # Current and target percentages at asset-class level for this account type
        at_code = self.at_cash.code
        at_data = cash_ac_entry.account_types[at_code]

        self.assertEqual(at_data.current_pct, Decimal("100.00"))
        self.assertEqual(at_data.target_pct, Decimal("100.00"))
        self.assertEqual(at_data.variance_pct, Decimal("0.00"))

        # Current and target dollars at asset-class level for this account type
        self.assertEqual(at_data.current, Decimal("50000.00"))
        self.assertEqual(at_data.target, Decimal("50000.00"))
        self.assertEqual(at_data.variance, Decimal("0.00"))

        # Per-account target dollars via account_asset_targets map
        ac_id = cash_ac_entry.id
        assert ac_id is not None
        acct_targets_for_account = summary.account_asset_targets[self.account_wf_cash.id]
        self.assertEqual(acct_targets_for_account[ac_id], Decimal("50000.00"))

        # Category-level per-account totals should be consistent
        cat_curr = cash_cat.account_totals[self.account_wf_cash.id]
        cat_target = cash_cat.account_target_totals[self.account_wf_cash.id]
        self.assertEqual(cat_curr, Decimal("50000.00"))
        self.assertEqual(cat_target, Decimal("50000.00"))
        self.assertEqual(cat_curr - cat_target, Decimal("0.00"))

        # And pre-calculated category variance for this account should match the same subtraction
        self.assertEqual(
            cash_cat.account_variance_totals[self.account_wf_cash.id],
            cat_curr - cat_target,
        )

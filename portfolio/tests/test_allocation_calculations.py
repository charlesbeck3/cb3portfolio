from decimal import Decimal
from typing import Any

from django.test import SimpleTestCase, TestCase

import pandas as pd

from portfolio.models import (
    Account,
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Holding,
    Institution,
    Portfolio,
    Security,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from users.models import CustomUser


class TestAllocationCalculationEngine(SimpleTestCase):
    """Test calculation engine with actual DataFrames."""

    def test_calculate_by_asset_class(self) -> None:
        """Engine calculates portfolio-wide asset class allocation."""
        # Create mock DataFrame
        # Cols: Asset_Class, Asset_Category, Security
        data = {
            ("Equities", "US Large Cap", "VTI"): [5000.0, 3000.0],
            ("Fixed Income", "Bonds", "BND"): [5000.0, 7000.0],
        }
        # Rows: Account_Type, Account_Category, Account_Name
        index = pd.MultiIndex.from_tuples(
            [("Taxable", "Brokerage", "Account1"), ("401k", "Retirement", "Account2")],
            names=["Account_Type", "Account_Category", "Account_Name"],
        )

        columns = pd.MultiIndex.from_tuples(
            data.keys(), names=["Asset_Class", "Asset_Category", "Security"]
        )

        df = pd.DataFrame(list(data.values()), index=columns).T
        df.columns = columns
        df.index = index

        # Calculate
        engine = AllocationCalculationEngine()
        result = engine._calculate_by_asset_class(df, df.sum().sum())

        # Verify
        assert "Equities" in result.index
        assert "Fixed Income" in result.index

        # Equities: 8000 / 20000 = 40%
        assert abs(result.loc["Equities", "Percentage"] - 40.0) < 0.1

        # Fixed Income: 12000 / 20000 = 60%
        assert abs(result.loc["Fixed Income", "Percentage"] - 60.0) < 0.1

        # Percentages sum to 100%
        assert abs(result["Percentage"].sum() - 100.0) < 0.01

    def test_calculate_by_account(self) -> None:
        """Engine calculates account-level allocations."""
        data = {
            ("Equities", "US Large Cap", "VTI"): [5000.0],
            ("Fixed Income", "Bonds", "BND"): [5000.0],
        }
        index = pd.MultiIndex.from_tuples(
            [
                ("Taxable", "Brokerage", "Account1"),
            ],
            names=["Account_Type", "Account_Category", "Account_Name"],
        )

        columns = pd.MultiIndex.from_tuples(
            data.keys(), names=["Asset_Class", "Asset_Category", "Security"]
        )

        df = pd.DataFrame(list(data.values()), index=columns).T
        df.columns = columns
        df.index = index

        engine = AllocationCalculationEngine()
        result = engine._calculate_by_account(df)

        # Should have _dollars and _pct for each asset class
        assert "Equities_dollars" in result.columns
        assert "Equities_pct" in result.columns
        assert "Fixed Income_dollars" in result.columns

        assert result.loc[("Taxable", "Brokerage", "Account1"), "Equities_pct"] == 50.0

    def test_calculate_allocations_empty(self) -> None:
        """Handles empty DataFrame gracefully."""
        df = pd.DataFrame()
        engine = AllocationCalculationEngine()
        result = engine.calculate_allocations(df)

        assert result["by_account"].empty
        assert result["portfolio_summary"].empty


class TestAllocationDashboardRows(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(username="testuser")
        self.portfolio = Portfolio.objects.create(user=self.user, name="Main Portfolio")

        # Setup Hierarchy: Group -> Category -> Asset Class
        # Group is just a parent Category
        self.group = AssetClassCategory.objects.create(
            label="Equities", code="EQUITIES", sort_order=1, parent=None
        )
        self.category = AssetClassCategory.objects.create(
            label="US Stocks", code="US_STOCKS", parent=self.group
        )
        self.asset_class = AssetClass.objects.create(name="Large Cap", category=self.category)

        self.cash_ac = AssetClass.objects.create(name="Cash", category=self.category)

        self.security = Security.objects.create(
            ticker="AAPL", name="Apple", asset_class=self.asset_class
        )

        self.type_taxable = AccountType.objects.create(
            label="Taxable", code="TAX", group=AccountGroup.objects.create(name="Liquid")
        )

        self.institution = Institution.objects.create(name="Fidelity")

        self.account = Account.objects.create(
            user=self.user,
            institution=self.institution,
            portfolio=self.portfolio,
            name="Brokerage",
            account_type=self.type_taxable,
        )

        # Test Data:
        # Holding: AAPL, $1500, Account: Brokerage (Taxable)
        Holding.objects.create(
            account=self.account,
            security=self.security,
            shares=Decimal("10"),
            current_price=Decimal("150.00"),
        )
        # Add Cash Holding?
        # For simplicity, just one holding. Cash row will be calculated as 0 if no cash holding is present and handled by logic.
        # But if we want to test Cash Row logic specifically with value:
        # We need to simulate cash holding or implicit cash?
        # The engine logic splits cash from holdings if present.

    def test_calculate_dashboard_rows_structure(self) -> None:
        # We need actual "Rich" account types as expected by the method
        # But for unit testing the engine, we can manually populate them or use mocks/minimal objects.

        # Manually populate rich AT
        # In a real scenario, this comes from views.
        type_taxable_any: Any = self.type_taxable
        type_taxable_any.current_total_value = Decimal("1500.00")
        type_taxable_any.target_map = {
            self.asset_class.id: Decimal("60")
        }  # 60% Target for Large Cap

        holdings_df = self.portfolio.to_dataframe()
        engine = AllocationCalculationEngine()

        rows = engine.calculate_dashboard_rows(
            holdings_df=holdings_df,
            account_types=[type_taxable_any],
            portfolio_total_value=Decimal("1500.00"),
            mode="dollar",
            cash_asset_class_id=self.cash_ac.id,
        )

        # Expected Rows:
        # 1. Large Cap Row
        #    Value: 1500. Target: 60% of 1500 = 900. Variance: +600.
        # 2. Subtotal (US Stocks Total)
        #    Value: 1500.
        # 3. Cash Row
        #    Value: 0. Target: Remainder? (100 - 60 = 40%). 40% of 1500 = 600. Variance: -600.
        # 4. Total
        #    Value: 1500. Target: 1500 (sum of targets 900+600).

        # Note: Group Total skipped because only 1 category.

        self.assertTrue(
            len(rows) >= 3, f"Got {len(rows)} rows: {[r.asset_class_name for r in rows]}"
        )

        # 1. Large Cap
        r_lc = next(r for r in rows if r.asset_class_name == "Large Cap")
        self.assertEqual(r_lc.portfolio_current, "$1,500")
        self.assertEqual(r_lc.portfolio_target, "$900")

        # Check Account Type Column
        at_col = r_lc.account_type_data[0]  # Taxable
        self.assertEqual(at_col.current, "$1,500")
        self.assertEqual(at_col.target, "$900")

        # 3. Cash Row
        r_cash = next(r for r in rows if r.is_cash)
        self.assertEqual(r_cash.asset_class_name, "Cash")
        self.assertEqual(r_cash.portfolio_current, "$0")
        self.assertEqual(r_cash.portfolio_target, "$600")

        at_col_cash = r_cash.account_type_data[0]
        self.assertEqual(at_col_cash.target, "$600")

        # 4. Total
        r_total = next(r for r in rows if r.is_grand_total)
        self.assertEqual(r_total.portfolio_current, "$1,500")

    def test_calculate_dashboard_rows_percent_mode(self) -> None:
        type_taxable_any: Any = self.type_taxable
        type_taxable_any.current_total_value = Decimal("1500.00")
        type_taxable_any.target_map = {self.asset_class.id: Decimal("60")}

        holdings_df = self.portfolio.to_dataframe()
        engine = AllocationCalculationEngine()

        rows = engine.calculate_dashboard_rows(
            holdings_df=holdings_df,
            account_types=[type_taxable_any],
            portfolio_total_value=Decimal("1500.00"),
            mode="percent",
            cash_asset_class_id=self.cash_ac.id,
        )

        # Check Large Cap
        r_lc = next(r for r in rows if r.asset_class_name == "Large Cap")
        self.assertEqual(r_lc.portfolio_current, "100.0%")

        # Row Target Value = $900. Portfolio Total = $1500. 900/1500 = 60.0%
        self.assertEqual(r_lc.portfolio_target, "60.0%")

        at_col = r_lc.account_type_data[0]
        self.assertEqual(at_col.current, "100.0%")
        self.assertEqual(at_col.target, "60.0%")  # Only one account type, so matches portfolio


class TestHoldingsDetailCalculation(SimpleTestCase):
    def test_calculate_holdings_detail(self) -> None:
        """Test granular holdings detail calculation using Long DataFrame."""
        # 1. Setup Mock DF (Long Format)
        acc_id_1 = 1
        acc_id_2 = 2

        data = [
            # Acct1: VTI, AAPL
            {
                "Account_ID": acc_id_1,
                "Account_Name": "Acct1",
                "Account_Type": "Taxable",
                "Account_Category": "Brokerage",
                "Asset_Class": "Equities",
                "Asset_Category": "Large Cap",
                "Ticker": "VTI",
                "Security_Name": "Vanguard Total Stock",
                "Shares": 10.0,
                "Price": 100.0,
                "Value": 1000.0,
            },
            {
                "Account_ID": acc_id_1,
                "Account_Name": "Acct1",
                "Account_Type": "Taxable",
                "Account_Category": "Brokerage",
                "Asset_Class": "Equities",
                "Asset_Category": "Large Cap",
                "Ticker": "AAPL",
                "Security_Name": "Apple Inc",
                "Shares": 5.0,
                "Price": 100.0,
                "Value": 500.0,
            },
            # Acct2: BND
            {
                "Account_ID": acc_id_2,
                "Account_Name": "Acct2",
                "Account_Type": "Retirement",
                "Account_Category": "Roth",
                "Asset_Class": "Fixed Income",
                "Asset_Category": "Bonds",
                "Ticker": "BND",
                "Security_Name": "Vanguard Bond",
                "Shares": 20.0,
                "Price": 100.0,
                "Value": 2000.0,
            },
        ]

        df = pd.DataFrame(data)

        # 2. Setup Targets
        # Acct1: Equities Target 60% (of 1500 = 900)
        # Acct2: Fixed Income Target 100% (of 2000 = 2000)

        targets_map = {
            acc_id_1: {"Equities": Decimal("60.0")},
            acc_id_2: {"Fixed Income": Decimal("100.0")},
        }

        engine = AllocationCalculationEngine()
        res = engine.calculate_holdings_detail(df, targets_map)

        # 3. Assertions
        self.assertEqual(len(res), 3)

        # Sort by Account and Ticker for deterministic checks
        res = res.sort_values(["Account_ID", "Ticker"]).reset_index(drop=True)
        # Order:
        # 0: Acct1 AAPL
        # 1: Acct1 VTI
        # 2: Acct2 BND

        # Check AAPL (Acct1)
        r_aapl = res.iloc[0]
        self.assertEqual(r_aapl["Ticker"], "AAPL")
        self.assertEqual(r_aapl["Account_ID"], acc_id_1)
        self.assertEqual(r_aapl["Value"], 500.0)
        self.assertEqual(r_aapl["Shares"], 5.0)  # Preserved

        # Target Calculation:
        # Account Total = 1500.
        # Equities Target = 600 (not 900? Wait. 60% of 1500 = 900).
        # Asset Class Target Value = 900.
        # Two securities in class (VTI, AAPL).
        # Split equally = 450 each.
        self.assertAlmostEqual(r_aapl["Target_Value"], 450.0)
        self.assertAlmostEqual(r_aapl["Variance"], 500.0 - 450.0)

        # Check VTI (Acct1)
        r_vti = res.iloc[1]
        self.assertEqual(r_vti["Ticker"], "VTI")
        self.assertEqual(r_vti["Value"], 1000.0)
        self.assertAlmostEqual(r_vti["Target_Value"], 450.0)  # Equal split
        self.assertAlmostEqual(r_vti["Variance"], 1000.0 - 450.0)

        # Check BND (Acct2)
        r_bnd = res.iloc[2]
        self.assertEqual(r_bnd["Ticker"], "BND")
        self.assertEqual(r_bnd["Account_ID"], acc_id_2)
        self.assertEqual(r_bnd["Value"], 2000.0)
        # Target 100% of 2000 = 2000. One security.
        self.assertAlmostEqual(r_bnd["Target_Value"], 2000.0)
        self.assertAlmostEqual(r_bnd["Variance"], 0.0)

from django.test import SimpleTestCase

import pandas as pd

from portfolio.services.allocation_calculations import AllocationCalculationEngine


class TestAllocationCalculationEngine(SimpleTestCase):
    """Test calculation engine with actual DataFrames."""

    def test_calculate_by_asset_class(self) -> None:
        """Engine calculates portfolio-wide asset class allocation."""
        # Create mock DataFrame
        # Cols: Asset_Class, Asset_Category, Security
        data = {
            ('Equities', 'US Large Cap', 'VTI'): [5000.0, 3000.0],
            ('Fixed Income', 'Bonds', 'BND'): [5000.0, 7000.0]
        }
        # Rows: Account_Type, Account_Category, Account_Name
        index = pd.MultiIndex.from_tuples([
            ('Taxable', 'Brokerage', 'Account1'),
            ('401k', 'Retirement', 'Account2')
        ], names=['Account_Type', 'Account_Category', 'Account_Name'])

        columns = pd.MultiIndex.from_tuples(
            data.keys(),
            names=['Asset_Class', 'Asset_Category', 'Security']
        )

        df = pd.DataFrame(list(data.values()), index=columns).T
        df.columns = columns
        df.index = index

        # Calculate
        engine = AllocationCalculationEngine()
        result = engine._calculate_by_asset_class(df, df.sum().sum())

        # Verify
        assert 'Equities' in result.index
        assert 'Fixed Income' in result.index

        # Equities: 8000 / 20000 = 40%
        assert abs(result.loc['Equities', 'Percentage'] - 40.0) < 0.1

        # Fixed Income: 12000 / 20000 = 60%
        assert abs(result.loc['Fixed Income', 'Percentage'] - 60.0) < 0.1

        # Percentages sum to 100%
        assert abs(result['Percentage'].sum() - 100.0) < 0.01

    def test_calculate_by_account(self) -> None:
        """Engine calculates account-level allocations."""
        data = {
            ('Equities', 'US Large Cap', 'VTI'): [5000.0],
            ('Fixed Income', 'Bonds', 'BND'): [5000.0]
        }
        index = pd.MultiIndex.from_tuples([
            ('Taxable', 'Brokerage', 'Account1'),
        ], names=['Account_Type', 'Account_Category', 'Account_Name'])

        columns = pd.MultiIndex.from_tuples(
            data.keys(),
            names=['Asset_Class', 'Asset_Category', 'Security']
        )

        df = pd.DataFrame(list(data.values()), index=columns).T
        df.columns = columns
        df.index = index

        engine = AllocationCalculationEngine()
        result = engine._calculate_by_account(df)

        # Should have _dollars and _pct for each asset class
        assert 'Equities_dollars' in result.columns
        assert 'Equities_pct' in result.columns
        assert 'Fixed Income_dollars' in result.columns

        assert result.loc[('Taxable', 'Brokerage', 'Account1'), 'Equities_pct'] == 50.0

    def test_calculate_allocations_empty(self) -> None:
        """Handles empty DataFrame gracefully."""
        df = pd.DataFrame()
        engine = AllocationCalculationEngine()
        result = engine.calculate_allocations(df)

        assert result['by_account'].empty
        assert result['portfolio_summary'].empty

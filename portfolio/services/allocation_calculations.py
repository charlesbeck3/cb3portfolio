"""
Pure pandas-based allocation calculations using MultiIndex DataFrames.
Zero Django dependencies - can be tested with mock DataFrames.
"""


import pandas as pd


class AllocationCalculationEngine:
    """
    Calculate portfolio allocations at all hierarchy levels.

    Uses pandas groupby operations on MultiIndex for clean aggregation.
    """

    def calculate_allocations(
        self,
        holdings_df: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        """
        Calculate allocations at all levels from portfolio holdings.

        Args:
            holdings_df: MultiIndex DataFrame from Portfolio.to_dataframe()
                Rows: (Account_Type, Account_Category, Account_Name)
                Cols: (Asset_Class, Asset_Category, Security)
                Values: Dollar amounts

        Returns:
            Dict with allocation DataFrames:
            - 'by_account': Allocation for each account
            - 'by_account_type': Allocation for each account type
            - 'by_asset_class': Portfolio-wide by asset class
            - 'portfolio_summary': Overall portfolio summary
        """
        if holdings_df.empty:
            return self._empty_allocations()

        total_value = float(holdings_df.sum().sum())

        return {
            "by_account": self._calculate_by_account(holdings_df),
            "by_account_type": self._calculate_by_account_type(holdings_df),
            "by_asset_class": self._calculate_by_asset_class(holdings_df, total_value),
            "portfolio_summary": self._calculate_portfolio_summary(
                holdings_df, total_value
            ),
        }

    def _calculate_by_account(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate allocation for each account.

        Returns:
            DataFrame with rows = accounts, columns = asset classes
            Shows both dollar amounts and percentages
        """
        # Group holdings by asset class within each account
        by_asset_class = df.T.groupby(level="Asset_Class").sum().T

        # Calculate account totals
        account_totals = by_asset_class.sum(axis=1)

        # Calculate percentages
        # Handle division by zero if an account has 0 value (though unlikely with holdings)
        percentages = by_asset_class.div(account_totals, axis=0).fillna(0.0) * 100

        # Combine into single DataFrame with MultiIndex columns
        result = pd.concat(
            [by_asset_class.add_suffix("_dollars"), percentages.add_suffix("_pct")],
            axis=1,
        )

        # Sort columns: all dollars first, then all percentages
        result = result.reindex(sorted(result.columns), axis=1)

        return result

    def _calculate_by_account_type(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate allocation for each account type.

        Aggregates across all accounts within each type.
        """
        # Sum all holdings within each account type
        by_type = df.groupby(level="Account_Type").sum()

        # Group by asset class
        by_asset_class = by_type.T.groupby(level="Asset_Class").sum().T

        # Calculate totals and percentages
        type_totals = by_asset_class.sum(axis=1)
        percentages = by_asset_class.div(type_totals, axis=0).fillna(0.0) * 100

        # Combine
        result = pd.concat(
            [by_asset_class.add_suffix("_dollars"), percentages.add_suffix("_pct")],
            axis=1,
        )

        result = result.reindex(sorted(result.columns), axis=1)

        return result

    def _calculate_by_asset_class(
        self,
        df: pd.DataFrame,
        total_value: float,
    ) -> pd.DataFrame:
        """
        Calculate portfolio-wide allocation by asset class.

        Returns:
            DataFrame with one row per asset class showing:
            - Dollar amount
            - Percentage of portfolio
        """
        if total_value == 0:
            return pd.DataFrame(columns=["Dollar_Amount", "Percentage"])

        # Sum across all accounts and securities within each asset class
        by_asset_class = df.T.groupby(level="Asset_Class").sum().T

        # Total for each asset class
        totals = by_asset_class.sum(axis=0)

        # Percentages
        percentages = (totals / total_value) * 100

        # Combine into result DataFrame
        result = pd.DataFrame(
            {
                "Dollar_Amount": totals,
                "Percentage": percentages,
            }
        )

        return result.sort_values("Dollar_Amount", ascending=False)

    def _calculate_portfolio_summary(
        self,
        df: pd.DataFrame,
        total_value: float,
    ) -> pd.DataFrame:
        """
        Calculate overall portfolio summary.

        Returns:
            Single-row DataFrame with portfolio totals
        """
        return pd.DataFrame(
            {
                "Total_Value": [total_value],
                "Number_of_Accounts": [len(df.index)],
                "Number_of_Holdings": [(df > 0).sum().sum()],
            }
        )

    def _empty_allocations(self) -> dict[str, pd.DataFrame]:
        """Return empty DataFrames for empty portfolio."""
        return {
            "by_account": pd.DataFrame(),
            "by_account_type": pd.DataFrame(),
            "by_asset_class": pd.DataFrame(),
            "portfolio_summary": pd.DataFrame(),
        }

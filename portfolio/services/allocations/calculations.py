"""Pure calculation logic using pandas vectorization."""

from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class AllocationCalculator:
    """
    Pure pandas calculations for allocations.

    All methods are stateless and operate on DataFrames.
    """

    def calculate_allocations(self, holdings_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """
        Calculate allocations at all hierarchy levels.

        Args:
            holdings_df: MultiIndex DataFrame from Portfolio.to_dataframe()
                Rows: (Account_Type, Account_Category, Account_Name, Account_ID)
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
            "by_account": self._aggregate_by_level(
                holdings_df, level="Account_ID", include_percentages=True
            ),
            "by_account_type": self._aggregate_by_level(
                holdings_df, level="Account_Type", include_percentages=True
            ),
            "by_asset_class": self._calculate_by_asset_class(holdings_df, total_value),
            "portfolio_summary": self._calculate_portfolio_summary(holdings_df, total_value),
        }

    def _aggregate_by_level(
        self,
        df: pd.DataFrame,
        level: str | list[str],
        include_percentages: bool = True,
    ) -> pd.DataFrame:
        """
        Universal aggregation method for any hierarchy level.

        Replaces _calculate_by_account, _calculate_by_account_type, etc.
        """
        # Group by asset class first
        by_asset = df.T.groupby(level="Asset_Class", observed=True).sum().T

        # Then group by specified level
        levels = [level] if isinstance(level, str) else level
        by_level = by_asset.groupby(level=levels, observed=True).sum()

        if not include_percentages:
            return by_level

        # Calculate percentages
        level_totals = by_level.sum(axis=1)
        percentages = by_level.div(level_totals, axis=0).fillna(0.0) * 100

        # Combine with _actual suffix
        result = pd.concat(
            [
                by_level.add_suffix("_actual"),
                percentages.add_suffix("_actual_pct"),
            ],
            axis=1,
        )

        return result.reindex(sorted(result.columns), axis=1)

    def _calculate_by_asset_class(self, df: pd.DataFrame, total_value: float) -> pd.DataFrame:
        """Calculate portfolio-wide allocation by asset class."""
        if total_value == 0:
            return pd.DataFrame(columns=["dollars", "percent"])

        # Sum across all accounts and securities
        by_asset = df.T.groupby(level="Asset_Class", observed=True).sum().T
        totals = by_asset.sum(axis=0)
        percentages = (totals / total_value) * 100

        result = pd.DataFrame(
            {
                "dollars": totals,
                "percent": percentages,
            }
        )

        return result.sort_values("dollars", ascending=False)

    def _calculate_portfolio_summary(self, df: pd.DataFrame, total_value: float) -> pd.DataFrame:
        """Calculate overall portfolio summary."""
        return pd.DataFrame(
            {
                "total_value": [total_value],
                "num_accounts": [len(df.index)],
                "num_holdings": [(df > 0).sum().sum()],
            }
        )

    def calculate_variances(
        self, actual_df: pd.DataFrame, targets_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate variances between actual and target allocations.

        Vectorized variance calculation using pandas merge and assign.
        """
        result = (
            actual_df.merge(
                targets_df,
                left_index=True,
                right_index=True,
                suffixes=("_actual", "_target"),
                how="outer",
            )
            .fillna(0.0)
            .assign(
                variance_value=lambda df: df.filter(like="_actual").sum(axis=1)
                - df.filter(like="_target").sum(axis=1),
                variance_pct=lambda df: (
                    df.filter(like="_actual").sum(axis=1)
                    / df.filter(like="_actual").sum(axis=1).sum()
                    * 100
                    - df.filter(like="_target").sum(axis=1)
                    / df.filter(like="_target").sum(axis=1).sum()
                    * 100
                ),
            )
        )

        return result

    def calculate_sidebar_metrics(
        self, holdings_df: pd.DataFrame, targets_map: dict[int, dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Calculate sidebar metrics using vectorized operations.

        Replaces the nested loop implementation in get_sidebar_data().

        Args:
            holdings_df: Long-format DataFrame with columns:
                account_id, asset_class, value
            targets_map: {account_id: {asset_class_name: target_pct}}

        Returns:
            Dict with:
                - account_totals: {account_id: total_value}
                - account_variances: {account_id: variance_pct}
                - grand_total: Total portfolio value
        """
        from decimal import Decimal

        if holdings_df.empty:
            return {
                "account_totals": {},
                "account_variances": {},
                "grand_total": Decimal("0.00"),
            }

        # Vectorized account totals
        account_totals = (
            holdings_df.groupby("account_id")["value"]
            .sum()
            .apply(lambda x: Decimal(str(x)))
            .to_dict()
        )

        # Vectorized variance calculation
        # Step 1: Create targets DataFrame for efficient merging
        targets_records = []
        for acc_id, allocations in targets_map.items():
            for asset_class, target_pct in allocations.items():
                targets_records.append(
                    {
                        "account_id": acc_id,
                        "asset_class": asset_class,
                        "target_pct": float(target_pct),
                    }
                )

        if targets_records:
            targets_df = pd.DataFrame(targets_records)

            # Step 2: Merge holdings with targets (true vectorization)
            holdings_with_targets = holdings_df.merge(
                targets_df, on=["account_id", "asset_class"], how="left"
            ).fillna({"target_pct": 0.0})
        else:
            holdings_with_targets = holdings_df.copy()
            holdings_with_targets["target_pct"] = 0.0

        # Step 3: Calculate target values and deviations
        account_totals_series = holdings_df.groupby("account_id")["value"].sum()
        holdings_with_targets["account_total"] = holdings_with_targets["account_id"].map(
            account_totals_series
        )
        holdings_with_targets["target_value"] = holdings_with_targets["account_total"] * (
            holdings_with_targets["target_pct"] / 100.0
        )
        holdings_with_targets["deviation"] = abs(
            holdings_with_targets["value"] - holdings_with_targets["target_value"]
        )

        # Step 4: Aggregate variances by account
        variances = (
            holdings_with_targets.groupby("account_id")
            .apply(
                lambda g: (
                    (g["deviation"].sum() / g["account_total"].iloc[0] * 100)
                    if g["account_total"].iloc[0] > 0
                    else 0.0
                ),
                include_groups=False,
            )
            .to_dict()
        )

        grand_total = sum(account_totals.values(), Decimal("0.00"))

        return {
            "account_totals": account_totals,
            "account_variances": variances,
            "grand_total": grand_total,
        }

    def _empty_allocations(self) -> dict[str, pd.DataFrame]:
        """Return empty DataFrames for empty portfolio."""
        return {
            "by_account": pd.DataFrame(),
            "by_account_type": pd.DataFrame(),
            "by_asset_class": pd.DataFrame(),
            "portfolio_summary": pd.DataFrame(),
        }

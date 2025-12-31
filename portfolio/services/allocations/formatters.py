"""Formatting layer for converting DataFrames to template-ready dicts."""

from typing import Any

import pandas as pd


class AllocationFormatter:
    """Format DataFrames into template-ready dictionary structures."""

    def to_presentation_rows(
        self, df: pd.DataFrame, metadata: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Transform DataFrame to presentation rows.

        Returns raw numeric values - templates handle formatting.
        """
        if df.empty:
            return []

        rows = []
        accounts_by_type = metadata.get("accounts_by_type", {})

        for idx, row in df.iterrows():
            # Extract MultiIndex values if present
            if isinstance(idx, tuple):
                group_code, category_code, asset_class_name = idx
            else:
                group_code = row.get("group_code", "")
                category_code = row.get("category_code", "")
                asset_class_name = str(idx)

            result = {
                "asset_class_name": asset_class_name,
                "asset_class_id": int(row.get("asset_class_id", 0)),
                "group_code": group_code,
                "category_code": category_code,
                "row_type": row.get("row_type", "asset"),
                "is_cash": bool(row.get("is_cash", False)),
                # Portfolio metrics (raw numerics)
                "portfolio": {
                    "actual": float(row.get("portfolio_actual", 0.0)),
                    "actual_pct": float(row.get("portfolio_actual_pct", 0.0)),
                    "effective": float(row.get("portfolio_effective", 0.0)),
                    "effective_pct": float(row.get("portfolio_effective_pct", 0.0)),
                    "effective_variance": float(row.get("portfolio_effective_variance", 0.0)),
                    "effective_variance_pct": float(
                        row.get("portfolio_effective_variance_pct", 0.0)
                    ),
                },
                # Account types
                "account_types": self._format_account_types(row, accounts_by_type),
            }

            rows.append(result)

        return rows

    def to_holdings_rows(self, df: pd.DataFrame) -> list[dict]:
        """Transform holdings DataFrame to rows."""
        if df.empty:
            return []

        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "row_type": "holding",
                    "ticker": row.get("ticker", ""),
                    "name": row.get("name", ""),
                    "value": float(row.get("value", 0.0)),
                    "target_value": float(row.get("target_value", 0.0)),
                    "value_variance": float(row.get("value_variance", 0.0)),
                    "shares": float(row.get("shares", 0.0)),
                    "target_shares": float(row.get("target_shares", 0.0)),
                    "shares_variance": float(row.get("shares_variance", 0.0)),
                    "is_holding": True,
                    "is_subtotal": False,
                }
            )

        return rows

    def _format_account_types(
        self, row: pd.Series, accounts_by_type: dict[int, list[dict]]
    ) -> list[dict]:
        """Format account type columns."""
        result = []

        for type_id, accounts in accounts_by_type.items():
            if not accounts:
                continue

            type_code = accounts[0]["type_code"]

            result.append(
                {
                    "id": type_id,
                    "code": type_code,
                    "label": accounts[0]["type_label"],
                    "actual": float(row.get(f"{type_code}_actual", 0.0)),
                    "actual_pct": float(row.get(f"{type_code}_actual_pct", 0.0)),
                    "effective": float(row.get(f"{type_code}_effective", 0.0)),
                    "effective_pct": float(row.get(f"{type_code}_effective_pct", 0.0)),
                }
            )

        return result

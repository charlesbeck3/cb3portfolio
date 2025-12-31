"""Formatting layer for converting DataFrames to template-ready dicts."""

from typing import Any

import pandas as pd


class AllocationFormatter:
    """Format DataFrames into template-ready dictionary structures."""

    def to_presentation_rows(
        self,
        df: pd.DataFrame,
        accounts_by_type: dict[int, list[dict]],
    ) -> list[dict[str, Any]]:
        """
        Transform presentation DataFrame to template-ready rows.

        Returns list of dicts with raw numeric values.
        Templates handle formatting via |money, |percent filters.

        Args:
            df: Presentation DataFrame from calculator
            accounts_by_type: Metadata about accounts grouped by type

        Returns:
            List of row dicts ready for template rendering
        """
        if df.empty:
            return []

        rows = []

        for _idx, row in df.iterrows():
            # Base row structure
            row_dict = {
                "asset_class_name": row["asset_class_name"],
                "asset_class_id": int(row["asset_class_id"]),
                "group_code": row.get("group_code", ""),
                "group_label": row.get("group_label", ""),
                "category_code": row.get("category_code", ""),
                "category_label": row.get("category_label", ""),
                "is_cash": bool(row.get("is_cash", False)),
                "row_type": row.get("row_type", "asset_class"),
                # Row type flags for template styling
                "is_subtotal": row.get("row_type") == "subtotal",
                "is_group_total": row.get("row_type") == "group_total",
                "is_grand_total": row.get("row_type") == "grand_total",
                # Portfolio metrics (raw numerics only)
                "portfolio": {
                    "actual": float(row.get("portfolio_actual", 0.0)),
                    "actual_pct": float(row.get("portfolio_actual_pct", 0.0)),
                    "effective": float(row.get("portfolio_effective", 0.0)),
                    "effective_pct": float(row.get("portfolio_effective_pct", 0.0)),
                    # Explicit target = same as effective for now (no separate policy targets)
                    "explicit_target": float(row.get("portfolio_effective", 0.0)),
                    "explicit_target_pct": float(row.get("portfolio_effective_pct", 0.0)),
                    "effective_variance": float(row.get("portfolio_variance", 0.0)),
                    "effective_variance_pct": float(row.get("portfolio_variance_pct", 0.0)),
                    # Policy variance = same as effective variance for now
                    "policy_variance": float(row.get("portfolio_variance", 0.0)),
                    "policy_variance_pct": float(row.get("portfolio_variance_pct", 0.0)),
                },
            }

            # Add account type data
            account_types = []
            for _type_id, accounts in accounts_by_type.items():
                if not accounts:
                    continue

                # Get type_code from first account in this type
                type_code = accounts[0].get("type_code", "")
                type_label = accounts[0].get("type_label", type_code)

                type_data = {
                    "code": type_code,
                    "label": type_label,
                    "actual": float(row.get(f"{type_code}_actual", 0.0)),
                    "actual_pct": float(row.get(f"{type_code}_actual_pct", 0.0)),
                    "effective": float(row.get(f"{type_code}_effective", 0.0)),
                    "effective_pct": float(row.get(f"{type_code}_effective_pct", 0.0)),
                    # Policy = same as effective for now (no separate policy targets)
                    "policy": float(row.get(f"{type_code}_effective", 0.0)),
                    "policy_pct": float(row.get(f"{type_code}_effective_pct", 0.0)),
                    "effective_variance": float(row.get(f"{type_code}_variance", 0.0)),
                    "effective_variance_pct": float(row.get(f"{type_code}_variance_pct", 0.0)),
                    # Policy variance = same as effective variance for now
                    "policy_variance": float(row.get(f"{type_code}_variance", 0.0)),
                    "policy_variance_pct": float(row.get(f"{type_code}_variance_pct", 0.0)),
                }
                account_types.append(type_data)

            row_dict["account_types"] = account_types

            # Add individual account data
            accounts = []
            for _type_id, type_accounts in accounts_by_type.items():
                for account in type_accounts:
                    acc_id = account["id"]
                    type_code = account.get("type_code", "")
                    account_data = {
                        "id": acc_id,
                        "name": account["name"],
                        "type_code": type_code,
                        "actual": float(row.get(f"account_{acc_id}_actual", 0.0)),
                        "actual_pct": float(row.get(f"account_{acc_id}_actual_pct", 0.0)),
                        "target": float(row.get(f"account_{acc_id}_target", 0.0)),
                        "target_pct": float(row.get(f"account_{acc_id}_target_pct", 0.0)),
                        "variance": float(row.get(f"account_{acc_id}_variance", 0.0)),
                        "variance_pct": float(row.get(f"account_{acc_id}_variance_pct", 0.0)),
                    }
                    accounts.append(account_data)

            row_dict["accounts"] = accounts
            rows.append(row_dict)

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

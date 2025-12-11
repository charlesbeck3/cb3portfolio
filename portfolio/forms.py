from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django import forms


class TargetAllocationForm(forms.Form):
    """Handles target allocation form submission for account-type defaults.

    This form mirrors the existing target_{at_id}_{ac_id} field naming
    convention used in TargetAllocationView and provides a parsed mapping of
    Decimal percentages per (account_type, asset_class) pair.
    """

    def __init__(
        self,
        *args: Any,
        account_types: Iterable[Any] | None = None,
        asset_classes: Iterable[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.account_types = list(account_types or [])
        self.asset_classes = list(asset_classes or [])

        # Dynamically add fields for each account type / asset class combo
        for at in self.account_types:
            for ac in self.asset_classes:
                field_name = f"target_{at.id}_{ac.id}"
                self.fields[field_name] = forms.DecimalField(
                    required=False,
                    min_value=0,
                    decimal_places=2,
                )

    def get_parsed_targets(self) -> dict[int, dict[int, Decimal]]:
        """Parse form data into structured target allocations.

        Returns:
            {account_type_id: {asset_class_id: pct_decimal}}
        """

        result: dict[int, dict[int, Decimal]] = {}

        for at in self.account_types:
            at_map: dict[int, Decimal] = {}

            for ac in self.asset_classes:
                field_name = f"target_{at.id}_{ac.id}"
                raw_value = self.cleaned_data.get(field_name)

                # Treat missing/empty as 0 to match existing view logic
                value: Decimal = raw_value if raw_value is not None else Decimal("0")
                at_map[ac.id] = value

            result[at.id] = at_map

        return result

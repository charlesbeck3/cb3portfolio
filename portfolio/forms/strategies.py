from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms

from portfolio.models import AllocationStrategy, AssetClass


class AllocationStrategyForm(forms.ModelForm):
    """Form for creating and editing Allocation Strategies."""

    class Meta:
        model = AllocationStrategy
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Get all asset classes including Cash
        all_asset_classes = (
            AssetClass.objects.select_related("category")
            .all()
            .order_by("category__sort_order", "category__label", "name")
        )

        # Separate cash from other asset classes
        self.asset_classes = []
        self.cash_asset_class = None

        for ac in all_asset_classes:
            if ac.is_cash():
                self.cash_asset_class = ac
            else:
                self.asset_classes.append(ac)

        # Dynamically add fields for each non-cash asset class
        for ac in self.asset_classes:
            field_name = f"target_{ac.id}"

            # If we're editing an existing strategy, pre-populate values
            initial_value = 0
            if self.instance.pk:
                target = self.instance.target_allocations.filter(asset_class=ac).first()
                if target:
                    initial_value = target.target_percent

            self.fields[field_name] = forms.DecimalField(
                label=ac.name,
                required=False,
                min_value=0,
                max_value=100,
                decimal_places=2,
                initial=initial_value,
                help_text=f"Target allocation for {ac.name} (%)",
            )

        # Add optional Cash field
        if self.cash_asset_class:
            field_name = f"target_{self.cash_asset_class.id}"
            initial_value = 0
            if self.instance.pk:
                target = self.instance.target_allocations.filter(
                    asset_class=self.cash_asset_class
                ).first()
                if target:
                    initial_value = target.target_percent

            self.fields[field_name] = forms.DecimalField(
                label="Cash (Optional)",
                required=False,
                min_value=0,
                max_value=100,
                decimal_places=2,
                initial=initial_value,
                help_text="Optional: Specify cash allocation explicitly. If omitted, calculated as remainder.",
            )

        self.fields["cash_note"] = forms.CharField(
            widget=forms.HiddenInput(),
            required=False,
            help_text="Cash allocation will be calculated automatically as the remainder if not specified",
        )

    def get_grouped_fields(self) -> list[tuple[str, list[forms.BoundField]]]:
        """Return fields grouped by Asset Class Category."""
        from collections import OrderedDict

        grouped: OrderedDict[str, list[forms.BoundField]] = OrderedDict()
        for ac in self.asset_classes:
            category_label = ac.category.label if ac.category else "Other"
            if category_label not in grouped:
                grouped[category_label] = []

            field_name = f"target_{ac.id}"
            grouped[category_label].append(self[field_name])

        return list(grouped.items())

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}

        total_allocation = Decimal("0.00")
        cash_provided = False

        # Calculate total including cash if provided
        for ac in self.asset_classes:
            field_name = f"target_{ac.id}"
            value = cleaned_data.get(field_name)
            if value:
                total_allocation += value

        # Check if cash was explicitly provided
        if self.cash_asset_class:
            cash_field_name = f"target_{self.cash_asset_class.id}"
            cash_value = cleaned_data.get(cash_field_name)
            if cash_value is not None and cash_value > 0:
                cash_provided = True
                total_allocation += cash_value

        # Validation logic
        if cash_provided:
            # User specified cash explicitly - must sum to exactly 100%
            if total_allocation != AllocationStrategy.TOTAL_ALLOCATION_PCT:
                raise forms.ValidationError(
                    f"When Cash is explicitly provided, total allocation must equal exactly {AllocationStrategy.TOTAL_ALLOCATION_PCT}%. "
                    f"Current total: {total_allocation}%"
                )
        else:
            # User omitted cash - total must not exceed 100%
            if total_allocation > AllocationStrategy.TOTAL_ALLOCATION_PCT:
                raise forms.ValidationError(
                    f"Total allocation ({total_allocation}%) cannot exceed {AllocationStrategy.TOTAL_ALLOCATION_PCT}%."
                )

        return cleaned_data

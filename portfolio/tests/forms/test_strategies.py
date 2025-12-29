from decimal import Decimal

import pytest

from portfolio.forms.strategies import AllocationStrategyForm
from portfolio.models import AllocationStrategy


@pytest.mark.django_db
@pytest.mark.forms
@pytest.mark.unit
class TestAllocationStrategyForm:
    """Test AllocationStrategyForm creation and validation."""

    def test_form_initialization(self, base_system_data):
        """Test that form creates dynamic fields for all asset classes."""
        form = AllocationStrategyForm()

        # Should have name and description
        assert "name" in form.fields
        assert "description" in form.fields

        # Should have dynamic fields for non-cash asset classes
        assert f"target_{base_system_data.asset_class_us_equities.id}" in form.fields
        assert f"target_{base_system_data.asset_class_treasuries_short.id}" in form.fields

        # Should have optional cash field
        cash_ac = base_system_data.asset_class_cash
        if cash_ac:
            assert f"target_{cash_ac.id}" in form.fields

    def test_valid_allocation_without_cash(self, base_system_data):
        """Test valid form submission without explicit cash (auto-calculated)."""
        form_data = {
            "name": "Test Strategy",
            "description": "Test Description",
            f"target_{base_system_data.asset_class_us_equities.id}": "60.00",
            f"target_{base_system_data.asset_class_treasuries_short.id}": "30.00",
            # Cash omitted - should be auto-calculated as 10%
        }
        form = AllocationStrategyForm(data=form_data)
        assert form.is_valid(), form.errors

    def test_valid_allocation_with_explicit_cash(self, base_system_data):
        """Test valid form with explicit cash allocation."""
        cash_ac = base_system_data.asset_class_cash
        form_data = {
            "name": "Test Strategy",
            "description": "Test",
            f"target_{base_system_data.asset_class_us_equities.id}": "60.00",
            f"target_{base_system_data.asset_class_treasuries_short.id}": "30.00",
            f"target_{cash_ac.id}": "10.00",  # Explicit cash
        }
        form = AllocationStrategyForm(data=form_data)
        assert form.is_valid(), form.errors

    def test_total_exceeds_100_without_cash(self, base_system_data):
        """Test validation fails when total > 100% without explicit cash."""
        form_data = {
            "name": "Test Strategy",
            "description": "Test",
            f"target_{base_system_data.asset_class_us_equities.id}": "60.00",
            f"target_{base_system_data.asset_class_treasuries_short.id}": "50.00",
            # Total = 110% without cash
        }
        form = AllocationStrategyForm(data=form_data)
        assert not form.is_valid()
        # Check that error message is present (case-insensitive, ignoring trailing punctuation)
        error_msg = str(form.non_field_errors()).lower()
        assert "cannot exceed 100" in error_msg

    def test_total_not_100_with_explicit_cash(self, base_system_data):
        """Test validation fails when cash provided but total != 100%."""
        cash_ac = base_system_data.asset_class_cash
        form_data = {
            "name": "Test Strategy",
            "description": "Test",
            f"target_{base_system_data.asset_class_us_equities.id}": "60.00",
            f"target_{base_system_data.asset_class_treasuries_short.id}": "30.00",
            f"target_{cash_ac.id}": "5.00",  # Total = 95%, should be 100%
        }
        form = AllocationStrategyForm(data=form_data)
        assert not form.is_valid()
        error_msg = str(form.non_field_errors()).lower()
        assert "must equal exactly 100" in error_msg

    def test_all_zero_allocations(self, base_system_data):
        """Test form with all zero allocations (edge case)."""
        form_data = {
            "name": "Empty Strategy",
            "description": "Test",
            f"target_{base_system_data.asset_class_us_equities.id}": "0.00",
            f"target_{base_system_data.asset_class_treasuries_short.id}": "0.00",
        }
        form = AllocationStrategyForm(data=form_data)
        # Should be valid - cash will be 100%
        assert form.is_valid(), form.errors

    def test_negative_allocation(self, base_system_data):
        """Test validation fails with negative allocation."""
        form_data = {
            "name": "Test Strategy",
            "description": "Test",
            f"target_{base_system_data.asset_class_us_equities.id}": "-10.00",
        }
        form = AllocationStrategyForm(data=form_data)
        assert not form.is_valid()

    def test_edit_existing_strategy(self, test_user, base_system_data):
        """Test form pre-populates when editing existing strategy."""
        # Create existing strategy
        strategy = AllocationStrategy.objects.create(user=test_user, name="Existing")

        # Save allocations manually since form uses many-to-many through model logic
        from portfolio.models.strategies import TargetAllocation

        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=base_system_data.asset_class_us_equities,
            target_percent=Decimal("70.00"),
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=base_system_data.asset_class_treasuries_short,
            target_percent=Decimal("30.00"),
        )

        # Initialize form with instance
        form = AllocationStrategyForm(instance=strategy)

        # Should pre-populate fields
        us_field = f"target_{base_system_data.asset_class_us_equities.id}"
        assert form.fields[us_field].initial == Decimal("70.00")

    def test_get_grouped_fields_method(self, base_system_data):
        """Test get_grouped_fields returns fields grouped by category."""
        form = AllocationStrategyForm()
        grouped = form.get_grouped_fields()

        # Should return list of (category_label, [fields])
        assert isinstance(grouped, list)
        assert len(grouped) > 0

        category_label, fields = grouped[0]
        assert isinstance(category_label, str)
        assert isinstance(fields, list)

    def test_missing_name_field(self, base_system_data):
        """Test validation fails without strategy name."""
        form_data = {
            "description": "Test",
            f"target_{base_system_data.asset_class_us_equities.id}": "100.00",
        }
        form = AllocationStrategyForm(data=form_data)
        assert not form.is_valid()
        assert "name" in form.errors

    def test_decimal_precision(self, base_system_data):
        """Test that allocations respect 2 decimal places."""
        form_data = {
            "name": "Precision Test",
            "description": "Test",
            f"target_{base_system_data.asset_class_us_equities.id}": "33.33",
            f"target_{base_system_data.asset_class_treasuries_short.id}": "33.33",
            # Cash auto = 33.34%
        }
        form = AllocationStrategyForm(data=form_data)
        assert form.is_valid(), form.errors

        # Test invalid precision
        form_data_invalid = {
            "name": "Precision Test Invalid",
            f"target_{base_system_data.asset_class_us_equities.id}": "33.333",
        }
        form_invalid = AllocationStrategyForm(data=form_data_invalid)
        assert not form_invalid.is_valid()

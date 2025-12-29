from decimal import Decimal

import pytest

from portfolio.forms.allocations import TargetAllocationForm


@pytest.mark.django_db
@pytest.mark.forms
@pytest.mark.unit
class TestTargetAllocationForm:
    """Test TargetAllocationForm validation and parsing."""

    def test_form_initialization(self, base_system_data):
        """Test that form creates dynamic fields for account types and asset classes."""
        account_types = [base_system_data.type_roth, base_system_data.type_taxable]
        asset_classes = [
            base_system_data.asset_class_us_equities,
            base_system_data.asset_class_cash,
        ]

        form = TargetAllocationForm(account_types=account_types, asset_classes=asset_classes)

        # Should have 2x2 = 4 fields
        for at in account_types:
            for ac in asset_classes:
                field_name = f"target_{at.id}_{ac.id}"
                assert field_name in form.fields

    def test_parse_targets(self, base_system_data):
        """Test that get_parsed_targets returns correct structure."""
        at_roth = base_system_data.type_roth
        at_tax = base_system_data.type_taxable
        ac_us = base_system_data.asset_class_us_equities
        ac_cash = base_system_data.asset_class_cash

        form_data = {
            f"target_{at_roth.id}_{ac_us.id}": "60.00",
            f"target_{at_roth.id}_{ac_cash.id}": "40.00",
            f"target_{at_tax.id}_{ac_us.id}": "70.00",
            f"target_{at_tax.id}_{ac_cash.id}": "30.00",
        }

        form = TargetAllocationForm(
            data=form_data, account_types=[at_roth, at_tax], asset_classes=[ac_us, ac_cash]
        )

        assert form.is_valid(), form.errors
        parsed = form.get_parsed_targets()

        assert parsed[at_roth.id][ac_us.id] == Decimal("60.00")
        assert parsed[at_roth.id][ac_cash.id] == Decimal("40.00")
        assert parsed[at_tax.id][ac_us.id] == Decimal("70.00")
        assert parsed[at_tax.id][ac_cash.id] == Decimal("30.00")

    def test_parse_missing_values_as_zero(self, base_system_data):
        """Test that missing fields are parsed as zero."""
        at_roth = base_system_data.type_roth
        ac_us = base_system_data.asset_class_us_equities

        form_data = {
            f"target_{at_roth.id}_{ac_us.id}": "60.00",
            # target_{at_roth.id}_{ac_cash.id} is missing
        }

        form = TargetAllocationForm(
            data=form_data,
            account_types=[at_roth],
            asset_classes=[ac_us, base_system_data.asset_class_cash],
        )

        assert form.is_valid()
        parsed = form.get_parsed_targets()

        assert parsed[at_roth.id][ac_us.id] == Decimal("60.00")
        assert parsed[at_roth.id][base_system_data.asset_class_cash.id] == Decimal("0")

    def test_invalid_decimal(self, base_system_data):
        """Test validation fails with invalid decimal input."""
        at_roth = base_system_data.type_roth
        ac_us = base_system_data.asset_class_us_equities

        form_data = {
            f"target_{at_roth.id}_{ac_us.id}": "not-a-number",
        }

        form = TargetAllocationForm(data=form_data, account_types=[at_roth], asset_classes=[ac_us])

        assert not form.is_valid()
        assert f"target_{at_roth.id}_{ac_us.id}" in form.errors

    def test_negative_value(self, base_system_data):
        """Test validation fails with negative value."""
        at_roth = base_system_data.type_roth
        ac_us = base_system_data.asset_class_us_equities

        form_data = {
            f"target_{at_roth.id}_{ac_us.id}": "-10.00",
        }

        form = TargetAllocationForm(data=form_data, account_types=[at_roth], asset_classes=[ac_us])

        assert not form.is_valid()
        assert f"target_{at_roth.id}_{ac_us.id}" in form.errors

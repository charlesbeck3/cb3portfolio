from decimal import Decimal

import pytest

from portfolio.forms.holdings import AddHoldingForm


@pytest.mark.django_db
@pytest.mark.unit
@pytest.mark.forms
class TestAddHoldingForm:
    """Test AddHoldingForm validation."""

    def test_valid_form(self, base_system_data):
        """Test form with valid data."""
        form = AddHoldingForm(
            data={
                "security_id": base_system_data.vti.id,
                "initial_shares": "10.50",
            }
        )
        assert form.is_valid()
        assert form.cleaned_data["security_id"] == base_system_data.vti.id
        assert form.cleaned_data["initial_shares"] == Decimal("10.50")

    def test_missing_security_id(self):
        """Test form validation fails without security_id."""
        form = AddHoldingForm(data={"initial_shares": "10.00"})
        assert not form.is_valid()
        assert "security_id" in form.errors

    def test_missing_initial_shares(self, base_system_data):
        """Test form validation fails without initial_shares."""
        form = AddHoldingForm(data={"security_id": base_system_data.vti.id})
        assert not form.is_valid()
        assert "initial_shares" in form.errors

    def test_invalid_security_id(self):
        """Test form validation fails with non-existent security."""
        form = AddHoldingForm(data={"security_id": 99999, "initial_shares": "10.00"})
        assert not form.is_valid()
        assert "security_id" in form.errors
        assert "Security not found" in str(form.errors["security_id"])

    def test_negative_shares(self, base_system_data):
        """Test form validation fails with negative shares."""
        form = AddHoldingForm(
            data={"security_id": base_system_data.vti.id, "initial_shares": "-5.00"}
        )
        assert not form.is_valid()
        assert "initial_shares" in form.errors

    def test_zero_shares_allowed(self, base_system_data):
        """Test that zero shares is valid (edge case)."""
        form = AddHoldingForm(
            data={"security_id": base_system_data.vti.id, "initial_shares": "0.00"}
        )
        assert form.is_valid()

    def test_shares_decimal_precision(self, base_system_data):
        """Test that shares respect decimal_places=2 constraint."""
        # Valid: 2 decimal places
        form = AddHoldingForm(
            data={"security_id": base_system_data.vti.id, "initial_shares": "10.12"}
        )
        assert form.is_valid()

        # Should fail if more than 2 decimals are provided (Django doesn't auto-round in form)
        form2 = AddHoldingForm(
            data={"security_id": base_system_data.vti.id, "initial_shares": "10.123"}
        )
        assert not form2.is_valid()
        assert "initial_shares" in form2.errors

    def test_large_share_count(self, base_system_data):
        """Test form handles large share counts."""
        form = AddHoldingForm(
            data={"security_id": base_system_data.vti.id, "initial_shares": "999999.99"}
        )
        assert form.is_valid()

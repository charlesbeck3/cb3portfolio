from decimal import Decimal
from typing import Any

import pytest

from portfolio.models import AssetClass, Security


@pytest.mark.models
@pytest.mark.integration
def test_create_asset_class(base_system_data: Any) -> None:
    """Test creating an asset class."""
    us_equities = base_system_data.cat_us_eq
    ac = AssetClass.objects.create(
        name="US Stocks Test", category=us_equities, expected_return=Decimal("0.08")
    )
    assert ac.name == "US Stocks Test"
    assert ac.expected_return == Decimal("0.08")
    assert str(ac) == "US Stocks Test"


@pytest.mark.models
@pytest.mark.unit
class TestAssetClassPrimarySecurity:
    """Test primary security relationship on AssetClass."""

    def test_primary_security_initially_none(self, base_system_data: Any) -> None:
        """Test that asset classes start without a primary security."""
        # Create a FRESH asset class to test default state
        # (System asset classes might already have primaries set by seeder)
        ac = AssetClass.objects.create(name="Test Asset Class", category=base_system_data.cat_us_eq)

        assert ac.primary_security is None

    def test_set_primary_security(self, base_system_data: Any) -> None:
        """Test setting and retrieving primary security."""
        # Create fresh asset class
        ac = AssetClass.objects.create(
            name="Test Asset Class 2", category=base_system_data.cat_us_eq
        )

        # Create VTI security
        vti = Security.objects.create(
            ticker="VTI_TEST",
            name="Vanguard Total Stock Market ETF",
            asset_class=ac,
        )

        # Set primary
        ac.primary_security = vti
        ac.save()

        # Verify
        ac.refresh_from_db()
        assert ac.primary_security == vti
        assert ac.primary_security.ticker == "VTI_TEST"

    def test_primary_security_set_null_on_delete(self, base_system_data: Any) -> None:
        """Test that primary_security is set to NULL when security is deleted."""
        ac = AssetClass.objects.create(
            name="Test Asset Class 3", category=base_system_data.cat_us_eq
        )

        # Create security and set as primary
        test_sec = Security.objects.create(
            ticker="TEST_DEL",
            name="Test Security",
            asset_class=ac,
        )
        ac.primary_security = test_sec
        ac.save()

        # Delete security
        test_sec.delete()

        # Verify primary_security is now None
        ac.refresh_from_db()
        assert ac.primary_security is None

    def test_check_if_security_is_primary(self, base_system_data: Any) -> None:
        """Test checking if a security is primary via FK comparison."""
        ac = AssetClass.objects.create(
            name="Test Asset Class 4", category=base_system_data.cat_us_eq
        )

        vti = Security.objects.create(
            ticker="VTI_CHECK",
            name="Test VTI",
            asset_class=ac,
        )

        # Set as primary
        ac.primary_security = vti
        ac.save()

        # Refresh to get updated relationship
        ac.refresh_from_db()
        vti.refresh_from_db()

        # Check via direct FK comparison (natural direction)
        assert ac.primary_security == vti
        assert ac.primary_security_id == vti.id

    def test_check_if_security_is_not_primary(self, base_system_data: Any) -> None:
        """Test checking if a security is NOT primary via FK comparison."""
        ac = AssetClass.objects.create(
            name="Test Asset Class 5", category=base_system_data.cat_us_eq
        )

        vti = Security.objects.create(
            ticker="VTI_NOT",
            name="Test VTI",
            asset_class=ac,
        )
        voo = Security.objects.create(
            ticker="VOO_NOT",
            name="Test VOO",
            asset_class=ac,
        )

        # Set VTI as primary (not VOO)
        ac.primary_security = vti
        ac.save()

        # Refresh
        ac.refresh_from_db()
        vti.refresh_from_db()
        voo.refresh_from_db()

        # Check via direct FK comparison
        assert ac.primary_security == vti
        assert ac.primary_security != voo
        assert ac.primary_security_id == vti.id
        assert ac.primary_security_id != voo.id

    def test_security_check_when_no_primary_set(self, base_system_data: Any) -> None:
        """Test checking primary status when asset class has no primary."""
        ac = AssetClass.objects.create(
            name="Test Asset Class 6", category=base_system_data.cat_us_eq
        )

        sec = Security.objects.create(
            ticker="SEC_NO_PRI",
            name="Test Security",
            asset_class=ac,
        )

        # Don't set any primary
        assert ac.primary_security is None
        assert ac.primary_security != sec

    def test_change_primary_security(self, base_system_data: Any) -> None:
        """Test changing primary security from one to another."""
        ac = AssetClass.objects.create(
            name="Test Asset Class 7", category=base_system_data.cat_us_eq
        )

        sec1 = Security.objects.create(
            ticker="SEC1",
            name="Security 1",
            asset_class=ac,
        )
        sec2 = Security.objects.create(
            ticker="SEC2",
            name="Security 2",
            asset_class=ac,
        )

        # Set sec1 as primary
        ac.primary_security = sec1
        ac.save()

        ac.refresh_from_db()
        assert ac.primary_security == sec1
        assert ac.primary_security != sec2

        # Change to sec2
        ac.primary_security = sec2
        ac.save()

        ac.refresh_from_db()
        assert ac.primary_security == sec2
        assert ac.primary_security != sec1

    def test_multiple_asset_classes_different_primaries(self, base_system_data: Any) -> None:
        """Test that different asset classes can have different primary securities."""
        system = base_system_data

        # Use existing asset class for one, create fresh for another
        # Note: existing asset class might already have a primary, so we overwrite it
        ac_equity = system.asset_class_us_equities

        # Correctly use an available asset class from fixture
        ac_bond = system.asset_class_treasuries_interm

        sec_equity = Security.objects.create(
            ticker="VTI_MULTI",
            name="Test Equity ETF",
            asset_class=ac_equity,
        )
        sec_bond = Security.objects.create(
            ticker="BND_MULTI",
            name="Test Bond ETF",
            asset_class=ac_bond,
        )

        # Set primaries
        ac_equity.primary_security = sec_equity
        ac_equity.save()
        ac_bond.primary_security = sec_bond
        ac_bond.save()

        # Refresh
        ac_equity.refresh_from_db()
        ac_bond.refresh_from_db()

        # Check relationships
        assert ac_equity.primary_security == sec_equity
        assert ac_bond.primary_security == sec_bond

        # Verify they're not mixed up
        assert sec_equity.asset_class == ac_equity
        assert sec_bond.asset_class == ac_bond

"""Tests for SystemSeederService."""

import pytest

from portfolio.models import (
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Institution,
    Security,
)
from portfolio.services.seeder import SystemSeederService


@pytest.mark.integration
@pytest.mark.services
class TestSystemSeederService:
    """Test suite for SystemSeederService."""

    def test_run_creates_all_required_data(self, db):
        """Test that run() creates all required system data."""
        # Clear existing data to test seeder in isolation
        Institution.objects.all().delete()
        AccountGroup.objects.all().delete()
        AccountType.objects.all().delete()
        AssetClassCategory.objects.all().delete()
        AssetClass.objects.all().delete()
        Security.objects.all().delete()

        seeder = SystemSeederService()
        seeder.run()

        # Verify institutions created
        assert Institution.objects.filter(name="Vanguard").exists()

        # Verify account groups created
        assert AccountGroup.objects.filter(name="Retirement").exists()
        assert AccountGroup.objects.filter(name="Investments").exists()
        assert AccountGroup.objects.filter(name="Deposits").exists()

        # Verify account types created
        assert AccountType.objects.filter(code="ROTH_IRA").exists()
        assert AccountType.objects.filter(code="TRADITIONAL_IRA").exists()
        assert AccountType.objects.filter(code="TAXABLE").exists()
        assert AccountType.objects.filter(code="401K").exists()

        # Verify asset categories created
        assert AssetClassCategory.objects.filter(code="EQUITIES").exists()
        assert AssetClassCategory.objects.filter(code="FIXED_INCOME").exists()
        assert AssetClassCategory.objects.filter(code="CASH").exists()

        # Verify asset classes created
        assert AssetClass.objects.filter(name="US Equities").exists()
        assert AssetClass.objects.filter(name="International Developed Equities").exists()

        # Verify securities created
        assert Security.objects.filter(ticker="VTI").exists()
        assert Security.objects.filter(ticker="VXUS").exists()
        assert Security.objects.filter(ticker="BND").exists()
        assert Security.objects.filter(ticker="CASH").exists()

    def test_run_is_idempotent(self, db):
        """Test that running seeder multiple times doesn't create duplicates."""
        seeder = SystemSeederService()

        # Run twice
        seeder.run()
        first_count = Institution.objects.count()

        seeder.run()
        second_count = Institution.objects.count()

        # Counts should be the same
        assert first_count == second_count

    def test_institution_seeding(self, db):
        """Test institution seeding specifically."""
        Institution.objects.all().delete()

        seeder = SystemSeederService()
        seeder._seed_institutions()

        vanguard = Institution.objects.get(name="Vanguard")
        # Note: Institution model might not have code, just name, checking name is enough based on seeder impl
        assert vanguard.name == "Vanguard"

    def test_account_groups_seeding(self, db):
        """Test account groups seeding specifically."""
        AccountGroup.objects.all().delete()

        seeder = SystemSeederService()
        seeder._seed_account_groups()

        retirement = AccountGroup.objects.get(name="Retirement")
        # Based on seeder impl, code is not explicitly set in the dict, but name is
        assert retirement.sort_order == 2

    def test_account_types_seeding(self, db):
        """Test account types seeding with proper relationships."""
        AccountGroup.objects.all().delete()
        AccountType.objects.all().delete()

        seeder = SystemSeederService()
        seeder._seed_account_groups()
        seeder._seed_account_types()

        roth = AccountType.objects.get(code="ROTH_IRA")
        assert roth.label == "Roth IRA"
        assert roth.tax_treatment == "TAX_FREE"
        assert roth.group.name == "Retirement"

    def test_asset_categories_hierarchy(self, db):
        """Test asset categories are created with proper hierarchy."""
        AssetClassCategory.objects.all().delete()

        seeder = SystemSeederService()
        seeder._seed_asset_categories()

        equities = AssetClassCategory.objects.get(code="EQUITIES")
        us_equities = AssetClassCategory.objects.get(code="US_EQUITIES")

        # Verify hierarchy
        assert us_equities.parent == equities

    def test_asset_classes_with_categories(self, db):
        """Test asset classes are assigned to correct categories."""
        AssetClassCategory.objects.all().delete()
        AssetClass.objects.all().delete()

        seeder = SystemSeederService()
        seeder._seed_asset_categories()
        seeder._seed_asset_classes()

        us_equities_asset = AssetClass.objects.get(name="US Equities")
        us_equities_category = AssetClassCategory.objects.get(code="US_EQUITIES")

        assert us_equities_asset.category == us_equities_category

    def test_securities_with_asset_classes(self, db):
        """Test securities are linked to correct asset classes."""
        AssetClassCategory.objects.all().delete()
        AssetClass.objects.all().delete()
        Security.objects.all().delete()

        seeder = SystemSeederService()
        seeder._seed_asset_categories()
        seeder._seed_asset_classes()
        seeder._seed_securities()

        vti = Security.objects.get(ticker="VTI")
        us_equities = AssetClass.objects.get(name="US Equities")

        assert vti.asset_class == us_equities
        assert vti.name == "Vanguard Total Stock Market ETF"

    def test_cash_security_has_special_properties(self, db):
        """Test that CASH security is created with correct properties."""
        Security.objects.all().delete()
        AssetClass.objects.all().delete()
        AssetClassCategory.objects.all().delete()

        seeder = SystemSeederService()
        seeder._seed_asset_categories()
        seeder._seed_asset_classes()
        seeder._seed_securities()

        cash = Security.objects.get(ticker="CASH")
        cash_asset_class = AssetClass.objects.get(name=AssetClass.CASH_NAME)

        assert cash.asset_class == cash_asset_class
        assert cash.name == "Cash Holding"

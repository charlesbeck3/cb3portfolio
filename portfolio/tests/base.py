from typing import Any

from portfolio.models import (
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Institution,
    Portfolio,
    Security,
)


class PortfolioTestMixin:
    """
    Mixin to provide standard setup for legacy Django TestCase tests.

    For pytest tests, use the fixtures in conftest.py instead.
    This mixin is kept for backward compatibility with:
    - test_calculations/test_golden_reference.py
    - test_e2e/conftest.py
    """

    def create_portfolio(self, *, user: Any, name: str = "Test Portfolio") -> None:
        """Create a portfolio for the given user."""
        self.portfolio = Portfolio.objects.create(user=user, name=name)

    def setup_system_data(self) -> None:
        """
        Seed system data and populate mixin attributes for use in tests.

        This method seeds:
        - Institutions
        - Account Groups
        - Account Types
        - Asset Class Categories
        - Asset Classes
        - Securities

        All seeded objects are accessible as instance attributes.
        """
        from portfolio.services.seeder import SystemSeederService

        # Run the centralized seeder
        seeder = SystemSeederService()
        seeder.run()

        # Populate Institution
        self.institution = Institution.objects.get(name="Vanguard")

        # Populate Groups
        self.group_retirement = AccountGroup.objects.get(name="Retirement")
        self.group_investments = AccountGroup.objects.get(name="Investments")
        self.group_deposits = AccountGroup.objects.get(name="Deposits")

        # Populate Account Types
        self.type_roth = AccountType.objects.get(code="ROTH_IRA")
        self.type_trad = AccountType.objects.get(code="TRADITIONAL_IRA")
        self.type_taxable = AccountType.objects.get(code="TAXABLE")
        self.type_401k = AccountType.objects.get(code="401K")
        self.type_deposit = AccountType.objects.get(code="DEPOSIT")

        # Populate Asset Categories
        self.category_equities = AssetClassCategory.objects.get(code="EQUITIES")
        self.category_fixed_income = AssetClassCategory.objects.get(code="FIXED_INCOME")
        self.category_cash = AssetClassCategory.objects.get(code="CASH")
        self.category_us_equities = AssetClassCategory.objects.get(code="US_EQUITIES")
        self.category_international_equities = AssetClassCategory.objects.get(
            code="INTERNATIONAL_EQUITIES"
        )

        # Populate Asset Classes
        self.asset_class_us_equities = AssetClass.objects.get(name="US Equities")
        self.asset_class_intl_developed = AssetClass.objects.get(
            name="International Developed Equities"
        )
        self.asset_class_intl_emerging = AssetClass.objects.get(
            name="International Emerging Equities"
        )
        self.asset_class_treasuries_short = AssetClass.objects.get(name="US Treasuries - Short")
        self.asset_class_treasuries_interm = AssetClass.objects.get(
            name="US Treasuries - Intermediate"
        )
        self.asset_class_tips = AssetClass.objects.get(name="Inflation Adjusted Bond")
        self.asset_class_cash = AssetClass.objects.get(name=AssetClass.CASH_NAME)
        self.asset_class_us_real_estate = AssetClass.objects.get(name="US Real Estate")
        self.asset_class_us_small_cap_value = AssetClass.objects.get(
            name="US Small Cap Value Equities"
        )
        self.asset_class_us_quality = AssetClass.objects.get(name="US Quality Equities")

        # Populate Securities
        self.vti = Security.objects.get(ticker="VTI")
        self.vxus = Security.objects.get(ticker="VXUS")
        self.bnd = Security.objects.get(ticker="BND")
        self.vgsh = Security.objects.get(ticker="VGSH")
        self.cash = Security.objects.get(ticker="CASH")

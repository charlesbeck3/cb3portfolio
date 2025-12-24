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
    """Mixin to provide standard setup for Portfolio tests."""

    def create_portfolio(self, *, user: Any, name: str = "Test Portfolio") -> None:
        self.portfolio = Portfolio.objects.create(user=user, name=name)

    def setup_system_data(self) -> None:
        """Seed system data and populate mixin attributes for use in tests."""
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

        # Populate Types
        self.type_roth_ira = AccountType.objects.get(code="ROTH_IRA")
        self.type_traditional_ira = AccountType.objects.get(code="TRADITIONAL_IRA")
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
        self.asset_class_us_real_estate = AssetClass.objects.get(name="US Real Estate")
        self.asset_class_us_value = AssetClass.objects.get(name="US Value Equities")
        self.asset_class_us_dividend = AssetClass.objects.get(name="US Dividend Equities")
        self.asset_class_us_quality = AssetClass.objects.get(name="US Quality Equities")
        self.asset_class_us_small_cap_value = AssetClass.objects.get(
            name="US Small Cap Value Equities"
        )
        self.asset_class_intl_developed = AssetClass.objects.get(
            name="International Developed Equities"
        )
        self.asset_class_intl_emerging = AssetClass.objects.get(
            name="International Emerging Equities"
        )
        self.asset_class_treasuries_short = AssetClass.objects.get(name="US Treasuries - Short")
        self.asset_class_treasuries_intermediate = AssetClass.objects.get(
            name="US Treasuries - Intermediate"
        )
        self.asset_class_inflation_bond = AssetClass.objects.get(name="Inflation Adjusted Bond")
        self.asset_class_cash = AssetClass.objects.get(name=AssetClass.CASH_NAME)

        # --- Standard Securities ---
        self.vti = Security.objects.get(ticker="VTI")
        self.voo = Security.objects.get(ticker="VOO")
        self.vtv = Security.objects.get(ticker="VTV")
        self.vig = Security.objects.get(ticker="VIG")
        self.vea = Security.objects.get(ticker="VEA")
        self.vwo = Security.objects.get(ticker="VWO")
        self.bnd = Security.objects.get(ticker="BND")
        self.vtip = Security.objects.get(ticker="VTIP")
        self.ibond = Security.objects.get(ticker="IBOND")
        self.vxus = Security.objects.get(ticker="VXUS")
        self.sec_cash = Security.objects.get(ticker="CASH")

        # --- Backward Compatibility Aliases ---
        self.cat_eq = self.category_equities
        self.cat_fi = self.category_fixed_income
        self.cat_cash = self.category_cash
        self.cat_us_eq = self.category_us_equities
        self.cat_intl_eq = self.category_international_equities
        self.ac_us_eq = self.asset_class_us_equities
        self.ac_intl_dev = self.asset_class_intl_developed
        self.ac_intl_em = self.asset_class_intl_emerging
        self.ac_treasuries_short = self.asset_class_treasuries_short
        self.ac_treasuries_int = self.asset_class_treasuries_intermediate
        self.ac_inflation_bond = self.asset_class_inflation_bond
        self.ac_cash = self.asset_class_cash
        self.type_trad = self.type_traditional_ira
        self.type_roth = self.type_roth_ira
        self.group_retirement = self.group_retirement
        self.group_invest = self.group_investments
        self.group_dep = self.group_deposits

    def setup_portfolio_data(self) -> None:
        """Alias for backward compatibility."""
        self.setup_system_data()

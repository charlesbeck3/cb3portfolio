from decimal import Decimal
from typing import Any, Protocol

from portfolio.models import (
    AccountGroup,
    AccountType,
    AssetClass,
    AssetClassCategory,
    Institution,
    Security,
)


class Logger(Protocol):
    def write(self, msg: str) -> None: ...
    def success(self, msg: str) -> None: ...


class SilentLogger:
    def write(self, msg: str) -> None:
        pass

    def success(self, msg: str) -> None:
        pass


class SystemSeederService:
    """Service to seed system reference data (Asset Classes, Account Types, etc.)."""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger or SilentLogger()

    def run(self) -> None:
        """Execute the seeding process."""
        self.logger.write("Seeding System Data...")

        # 1. Account Groups
        self._seed_account_groups()

        # 2. Account Types
        self._seed_account_types()

        # 3. Asset Categories
        self._seed_asset_categories()

        # 4. Asset Classes
        self._seed_asset_classes()

        # 5. Securities
        self._seed_securities()

        # 6. Set Primary Securities
        self._set_primary_securities()

        #  institution
        self._seed_institutions()

        self.logger.success("System Data seeded successfully!")

    def _seed_account_groups(self) -> None:
        groups: list[dict[str, Any]] = [
            {"name": "Investments", "sort_order": 1},
            {"name": "Retirement", "sort_order": 2},
            {"name": "Deposits", "sort_order": 3},
        ]
        self.group_objects = {}
        for g_data in groups:
            group_obj, created = AccountGroup.objects.get_or_create(
                name=g_data["name"], defaults={"sort_order": g_data["sort_order"]}
            )
            self.group_objects[group_obj.name] = group_obj
            if created:
                self.logger.success(f"Created Group: {group_obj.name}")

    def _seed_account_types(self) -> None:
        types: list[dict[str, Any]] = [
            {
                "code": "TAXABLE",
                "label": "Taxable",
                "group": "Investments",
                "tax_treatment": "TAXABLE",
            },
            {
                "code": "TRADITIONAL_IRA",
                "label": "Traditional IRA",
                "group": "Retirement",
                "tax_treatment": "TAX_DEFERRED",
            },
            {
                "code": "ROTH_IRA",
                "label": "Roth IRA",
                "group": "Retirement",
                "tax_treatment": "TAX_FREE",
            },
            {
                "code": "401K",
                "label": "401(k)",
                "group": "Retirement",
                "tax_treatment": "TAX_DEFERRED",
            },
            {
                "code": "DEPOSIT",
                "label": "Deposit",
                "group": "Deposits",
                "tax_treatment": "TAXABLE",
            },
        ]
        for t_data in types:
            type_obj, created = AccountType.objects.update_or_create(
                code=t_data["code"],
                defaults={
                    "label": t_data["label"],
                    "group": self.group_objects[t_data["group"]],
                    "tax_treatment": t_data["tax_treatment"],
                },
            )
            if created:
                self.logger.success(f"Created Account Type: {type_obj.label}")

    def _seed_asset_categories(self) -> None:
        categories: list[dict[str, Any]] = [
            {"code": "EQUITIES", "label": "Equities", "parent": None, "sort_order": 1},
            {"code": "US_EQUITIES", "label": "US Equities", "parent": "EQUITIES", "sort_order": 2},
            {
                "code": "INTERNATIONAL_EQUITIES",
                "label": "International Equities",
                "parent": "EQUITIES",
                "sort_order": 3,
            },
            {
                "code": "CASH_AND_FIXED_INCOME",
                "label": "Cash and Fixed Income",
                "parent": None,
                "sort_order": 4,
            },
            {
                "code": "FIXED_INCOME",
                "label": "Fixed Income",
                "parent": "CASH_AND_FIXED_INCOME",
                "sort_order": 5,
            },
            {"code": "CASH", "label": "Cash", "parent": "CASH_AND_FIXED_INCOME", "sort_order": 6},
        ]
        self.category_objects: dict[str, AssetClassCategory] = {}
        for cat_data in categories:
            parent_code = cat_data["parent"]
            parent_obj = self.category_objects.get(parent_code) if parent_code else None
            cat_obj, created = AssetClassCategory.objects.update_or_create(
                code=cat_data["code"],
                defaults={
                    "label": cat_data["label"],
                    "parent": parent_obj,
                    "sort_order": cat_data["sort_order"],
                },
            )
            self.category_objects[cat_obj.code] = cat_obj
            if created:
                self.logger.success(f"Created Category: {cat_obj.label}")

    def _seed_asset_classes(self) -> None:
        asset_classes: list[dict[str, Any]] = [
            {"name": "US Equities", "category": "US_EQUITIES", "expected_return": Decimal("0.08")},
            {
                "name": "US Real Estate",
                "category": "US_EQUITIES",
                "expected_return": Decimal("0.06"),
            },
            {
                "name": "US Quality Equities",
                "category": "US_EQUITIES",
                "expected_return": Decimal("0.06"),
            },
            {
                "name": "US Small Cap Value Equities",
                "category": "US_EQUITIES",
                "expected_return": Decimal("0.06"),
            },
            {
                "name": "US Dividend Equities",
                "category": "US_EQUITIES",
                "expected_return": Decimal("0.07"),
            },
            {
                "name": "US Value Equities",
                "category": "US_EQUITIES",
                "expected_return": Decimal("0.075"),
            },
            {
                "name": "International Developed Equities",
                "category": "INTERNATIONAL_EQUITIES",
                "expected_return": Decimal("0.07"),
            },
            {
                "name": "International Emerging Equities",
                "category": "INTERNATIONAL_EQUITIES",
                "expected_return": Decimal("0.09"),
            },
            {
                "name": "US Treasuries - Short",
                "category": "FIXED_INCOME",
                "expected_return": Decimal("0.03"),
            },
            {
                "name": "US Treasuries - Intermediate",
                "category": "FIXED_INCOME",
                "expected_return": Decimal("0.04"),
            },
            {
                "name": "Inflation Adjusted Bond",
                "category": "FIXED_INCOME",
                "expected_return": Decimal("0.05"),
            },
            {
                "name": AssetClass.CASH_NAME,
                "category": "CASH",
                "expected_return": Decimal("0.02"),
            },
        ]
        for ac_data in asset_classes:
            category_obj = self.category_objects[ac_data["category"]]
            ac_obj, created = AssetClass.objects.get_or_create(
                name=ac_data["name"],
                defaults={
                    "expected_return": ac_data["expected_return"],
                    "category": category_obj,
                },
            )
            if created:
                self.logger.success(f"Created Asset Class: {ac_obj.name}")

    def _seed_securities(self) -> None:
        securities: list[dict[str, Any]] = [
            {
                "ticker": "VTI",
                "name": "Vanguard Total Stock Market ETF",
                "asset_class": "US Equities",
            },
            {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "asset_class": "US Equities"},
            {"ticker": "VTV", "name": "Vanguard Value ETF", "asset_class": "US Value Equities"},
            {
                "ticker": "VIG",
                "name": "Vanguard Dividend Appreciation ETF",
                "asset_class": "US Dividend Equities",
            },
            {"ticker": "VNQ", "name": "Vanguard Real Estate ETF", "asset_class": "US Real Estate"},
            {
                "ticker": "USRT",
                "name": "iShares Core U.S. REIT ETF",
                "asset_class": "US Real Estate",
            },
            {
                "ticker": "VEA",
                "name": "Vanguard FTSE Developed Markets ETF",
                "asset_class": "International Developed Equities",
            },
            {
                "ticker": "VWO",
                "name": "Vanguard FTSE Emerging Markets ETF",
                "asset_class": "International Emerging Equities",
            },
            {
                "ticker": "VGSH",
                "name": "Vanguard Short-Term Treasury ETF",
                "asset_class": "US Treasuries - Short",
            },
            {
                "ticker": "VGIT",
                "name": "Vanguard Intermediate-Term Treasury ETF",
                "asset_class": "US Treasuries - Intermediate",
            },
            {
                "ticker": "VTIP",
                "name": "Vanguard Short-Term Inflation-Protected Securities ETF",
                "asset_class": "US Treasuries - Short",
            },
            {
                "ticker": "IBOND",
                "name": "Series I Savings Bond",
                "asset_class": "Inflation Adjusted Bond",
            },
            {
                "ticker": "CASH",
                "name": "Cash Holding",
                "asset_class": AssetClass.CASH_NAME,
            },
            {
                "ticker": "VXUS",
                "name": "Vanguard Total International Stock ETF",
                "asset_class": "International Developed Equities",
            },
            {
                "ticker": "BND",
                "name": "Vanguard Total Bond Market ETF",
                "asset_class": "US Treasuries - Intermediate",
            },
            {
                "ticker": "AVUV",
                "name": "Avantis US Small Cap Value ETF",
                "asset_class": "US Small Cap Value Equities",
            },
            {
                "ticker": "JQUA",
                "name": "JPMorgan US Quality Factor ETF",
                "asset_class": "US Quality Equities",
            },
        ]
        for sec_data in securities:
            asset_class = AssetClass.objects.get(name=sec_data["asset_class"])
            sec_obj, created = Security.objects.update_or_create(
                ticker=sec_data["ticker"],
                defaults={"name": sec_data["name"], "asset_class": asset_class},
            )
            if created:
                self.logger.success(f"Created Security: {sec_obj.ticker}")

    def _seed_institutions(self) -> None:
        institutions = [
            "Bank of America",
            "Merrill Lynch",
            "Wealthfront",
            "Wells Fargo",
            "JP Morgan Chase",
            "Charles Schwab",
            "Citibank",
            "Treasury Direct",
            "Vanguard",
        ]
        for name in institutions:
            inst_obj, created = Institution.objects.get_or_create(name=name)
            if created:
                self.logger.success(f"Created Institution: {inst_obj.name}")

    def _set_primary_securities(self) -> None:
        """Set primary securities for asset classes."""
        primary_mappings = {
            "US Equities": "VTI",
            "US Small Cap Value Equities": "AVUV",
            "US Quality Equities": "JQUA",
            "US Dividend Equities": "VIG",
            "US Value Equities": "VTV",
            "US Real Estate": "VNQ",
            "International Developed Equities": "VEA",
            "International Emerging Equities": "VWO",
            "US Treasuries - Short": "VGSH",
            "US Treasuries - Intermediate": "VGIT",
            "Inflation Adjusted Bond": "IBOND",
            "Cash": "CASH",
        }

        updated_count = 0

        for ac_name, ticker in primary_mappings.items():
            try:
                asset_class = AssetClass.objects.get(name=ac_name)
                security = Security.objects.get(ticker=ticker)

                if asset_class.primary_security != security:
                    asset_class.primary_security = security
                    asset_class.save()
                    updated_count += 1
                    self.logger.success(f"Set primary for {ac_name}: {ticker}")

            except AssetClass.DoesNotExist:
                self.logger.write(f"Warning: Asset class not found: {ac_name}")
            except Security.DoesNotExist:
                self.logger.write(f"Warning: Security not found: {ticker}")

        self.logger.success(f"Updated {updated_count} primary securities")

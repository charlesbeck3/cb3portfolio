from typing import Any

from portfolio.models import AccountGroup, AccountType, AssetClassCategory, Institution, Portfolio


class PortfolioTestMixin:
    """Mixin to provide standard setup for Portfolio tests."""

    def create_portfolio(self, *, user: Any, name: str = "Test Portfolio") -> None:
        self.portfolio = Portfolio.objects.create(user=user, name=name)

    def setup_portfolio_data(self) -> None:
        # Create Institution
        self.institution, _ = Institution.objects.get_or_create(name="Test Bank")

        # Get or Create Groups
        self.group_ret, _ = AccountGroup.objects.get_or_create(
            name="Retirement", defaults={"sort_order": 1}
        )
        self.group_inv, _ = AccountGroup.objects.get_or_create(
            name="Investments", defaults={"sort_order": 2}
        )
        self.group_dep, _ = AccountGroup.objects.get_or_create(
            name="Deposit Accounts", defaults={"sort_order": 3}
        )

        # Get or Create Types
        self.type_roth, _ = AccountType.objects.get_or_create(
            code="ROTH_IRA",
            defaults={"label": "Roth IRA", "group": self.group_ret, "tax_treatment": "TAX_FREE"},
        )
        self.type_trad, _ = AccountType.objects.get_or_create(
            code="TRADITIONAL_IRA",
            defaults={
                "label": "Traditional IRA",
                "group": self.group_ret,
                "tax_treatment": "TAX_DEFERRED",
            },
        )
        self.type_taxable, _ = AccountType.objects.get_or_create(
            code="TAXABLE",
            defaults={"label": "Taxable", "group": self.group_inv, "tax_treatment": "TAXABLE"},
        )
        self.type_401k, _ = AccountType.objects.get_or_create(
            code="401K",
            defaults={"label": "401(k)", "group": self.group_ret, "tax_treatment": "TAX_DEFERRED"},
        )

        # Get or Create Asset Categories
        # Parent Categories
        self.cat_eq, _ = AssetClassCategory.objects.get_or_create(
            code="EQUITIES", defaults={"label": "Equities", "sort_order": 1}
        )
        self.cat_fi, _ = AssetClassCategory.objects.get_or_create(
            code="FIXED_INCOME", defaults={"label": "Fixed Income", "sort_order": 2}
        )
        self.cat_cash, _ = AssetClassCategory.objects.get_or_create(
            code="CASH", defaults={"label": "Cash", "sort_order": 3}
        )

        # Sub Categories
        self.cat_us_eq, _ = AssetClassCategory.objects.get_or_create(
            code="US_EQUITIES",
            defaults={"label": "US Equities", "parent": self.cat_eq, "sort_order": 1},
        )
        self.cat_intl_eq, _ = AssetClassCategory.objects.get_or_create(
            code="INTERNATIONAL_EQUITIES",
            defaults={"label": "International Equities", "parent": self.cat_eq, "sort_order": 2},
        )

from portfolio.models import AccountGroup, AccountType, Institution


class PortfolioTestMixin:
    """Mixin to provide standard setup for Portfolio tests."""

    def setup_portfolio_data(self) -> None:
        # Create Institution
        self.institution, _ = Institution.objects.get_or_create(name='Test Bank')

        # Get or Create Groups
        self.group_ret, _ = AccountGroup.objects.get_or_create(name='Retirement', defaults={'sort_order': 1})
        self.group_inv, _ = AccountGroup.objects.get_or_create(name='Investments', defaults={'sort_order': 2})
        self.group_dep, _ = AccountGroup.objects.get_or_create(name='Deposit Accounts', defaults={'sort_order': 3})

        # Get or Create Types
        self.type_roth, _ = AccountType.objects.get_or_create(
            code='ROTH_IRA',
            defaults={'label': 'Roth IRA', 'group': self.group_ret, 'tax_treatment': 'TAX_FREE'}
        )
        self.type_trad, _ = AccountType.objects.get_or_create(
            code='TRADITIONAL_IRA',
            defaults={'label': 'Traditional IRA', 'group': self.group_ret, 'tax_treatment': 'TAX_DEFERRED'}
        )
        self.type_taxable, _ = AccountType.objects.get_or_create(
            code='TAXABLE',
            defaults={'label': 'Taxable', 'group': self.group_inv, 'tax_treatment': 'TAXABLE'}
        )
        self.type_401k, _ = AccountType.objects.get_or_create(
            code='401K',
            defaults={'label': '401(k)', 'group': self.group_ret, 'tax_treatment': 'TAX_DEFERRED'}
        )

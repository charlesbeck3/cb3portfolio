import os
from decimal import Decimal
from typing import Any, TypedDict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portfolio.models import Account, AssetCategory, AssetClass, Holding, Security


class CategorySeed(TypedDict):
    code: str
    label: str
    parent: str | None
    sort_order: int


class AssetClassSeed(TypedDict):
    name: str
    category: str
    expected_return: Decimal


class SecuritySeed(TypedDict):
    ticker: str
    name: str
    asset_class: str

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds the database with standard Asset Classes and Securities'

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write('Seeding database...')

        # Create Superuser
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin')

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username, email, password)
            self.stdout.write(self.style.SUCCESS(f'Created superuser: {username}'))
        else:
            self.stdout.write(f'Superuser already exists: {username}')

        # Asset Categories (hierarchical)
        categories: list[CategorySeed] = [
            {'code': 'EQUITIES', 'label': 'Equities', 'parent': None, 'sort_order': 1},
            {'code': 'US_EQUITIES', 'label': 'US Equities', 'parent': 'EQUITIES', 'sort_order': 2},
            {'code': 'INTERNATIONAL_EQUITIES', 'label': 'International Equities', 'parent': 'EQUITIES', 'sort_order': 3},
            {'code': 'FIXED_INCOME', 'label': 'Fixed Income', 'parent': None, 'sort_order': 4},
            {'code': 'REAL_ASSETS', 'label': 'Real Assets', 'parent': None, 'sort_order': 5},
            {'code': 'CASH', 'label': 'Cash', 'parent': None, 'sort_order': 6},
        ]

        category_objects: dict[str, AssetCategory] = {}
        for cat_data in categories:
            parent_code = cat_data['parent']
            parent_obj = category_objects.get(parent_code) if parent_code else None
            cat_obj, created = AssetCategory.objects.update_or_create(
                code=cat_data['code'],
                defaults={
                    'label': cat_data['label'],
                    'parent': parent_obj,
                    'sort_order': cat_data['sort_order'],
                }
            )
            category_objects[cat_obj.code] = cat_obj
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created Category: {cat_obj.label}'))
            else:
                self.stdout.write(f'Category up to date: {cat_obj.label}')

        # Asset Classes
        asset_classes: list[AssetClassSeed] = [
            {'name': 'US Equities', 'category': 'US_EQUITIES', 'expected_return': Decimal('0.08')},
            {'name': 'US Real Estate', 'category': 'REAL_ASSETS', 'expected_return': Decimal('0.06')},
            {'name': 'US Dividend Equities', 'category': 'US_EQUITIES', 'expected_return': Decimal('0.07')},
            {'name': 'US Value Equities', 'category': 'US_EQUITIES', 'expected_return': Decimal('0.075')},
            {'name': 'International Developed Equities', 'category': 'INTERNATIONAL_EQUITIES', 'expected_return': Decimal('0.07')},
            {'name': 'International Emerging Equities', 'category': 'INTERNATIONAL_EQUITIES', 'expected_return': Decimal('0.09')},
            {'name': 'US Short-term Treasuries', 'category': 'FIXED_INCOME', 'expected_return': Decimal('0.03')},
            {'name': 'US Intermediate-term Treasuries', 'category': 'FIXED_INCOME', 'expected_return': Decimal('0.04')},
            {'name': 'Inflation Adjusted Bond', 'category': 'FIXED_INCOME', 'expected_return': Decimal('0.05')},
            {'name': 'Cash', 'category': 'CASH', 'expected_return': Decimal('0.02')},
        ]

        for ac_data in asset_classes:
            category_obj = category_objects[ac_data['category']]
            ac_obj, created = AssetClass.objects.get_or_create(
                name=ac_data['name'],
                defaults={
                    'expected_return': ac_data['expected_return'],
                    'category': category_obj,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created Asset Class: {ac_obj.name}'))
            else:
                updated_fields = []
                if ac_obj.category_id != category_obj.code:
                    ac_obj.category = category_obj
                    updated_fields.append('category')
                if ac_obj.expected_return != ac_data['expected_return']:
                    ac_obj.expected_return = ac_data['expected_return']
                    updated_fields.append('expected_return')

                if updated_fields:
                    ac_obj.save(update_fields=updated_fields)
                    self.stdout.write(
                        self.style.SUCCESS(f'Updated Asset Class: {ac_obj.name} ({', '.join(updated_fields)})')
                    )
                else:
                    self.stdout.write(f'Asset Class already up to date: {ac_obj.name}')

        # Securities
        securities: list[SecuritySeed] = [
            {'ticker': 'VTI', 'name': 'Vanguard Total Stock Market ETF', 'asset_class': 'US Equities'},
            {'ticker': 'VOO', 'name': 'Vanguard S&P 500 ETF', 'asset_class': 'US Equities'},
            {'ticker': 'VTV', 'name': 'Vanguard Value ETF', 'asset_class': 'US Value Equities'},
            {'ticker': 'VIG', 'name': 'Vanguard Dividend Appreciation ETF', 'asset_class': 'US Dividend Equities'},
            {'ticker': 'VNQ', 'name': 'Vanguard Real Estate ETF', 'asset_class': 'US Real Estate'},
            {'ticker': 'USRT', 'name': 'iShares Core U.S. REIT ETF', 'asset_class': 'US Real Estate'},
            {'ticker': 'VEA', 'name': 'Vanguard FTSE Developed Markets ETF', 'asset_class': 'International Developed Equities'},
            {'ticker': 'VWO', 'name': 'Vanguard FTSE Emerging Markets ETF', 'asset_class': 'International Emerging Equities'},
            {'ticker': 'VGSH', 'name': 'Vanguard Short-Term Treasury ETF', 'asset_class': 'US Short-term Treasuries'},
            {'ticker': 'VGIT', 'name': 'Vanguard Intermediate-Term Treasury ETF', 'asset_class': 'US Intermediate-term Treasuries'},
            {'ticker': 'VTIP', 'name': 'Vanguard Short-Term Inflation-Protected Securities ETF', 'asset_class': 'US Short-term Treasuries'},
            {'ticker': 'IBOND', 'name': 'Series I Savings Bond', 'asset_class': 'Inflation Adjusted Bond'},
            {'ticker': 'CASH', 'name': 'Cash Holding', 'asset_class': 'Cash'},
        ]

        for sec_data in securities:
            asset_class = AssetClass.objects.get(name=sec_data['asset_class'])
            sec_obj, created = Security.objects.update_or_create(
                ticker=sec_data['ticker'],
                defaults={
                    'name': sec_data['name'],
                    'asset_class': asset_class
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created Security: {sec_obj.ticker}'))
            else:
                self.stdout.write(f'Updated Security: {sec_obj.ticker}')

        admin_user = User.objects.get(username=username)

        account_rows: list[dict[str, Any]] = [
            {
                'name': 'Treasury Direct',
                'account_subtype': 'Taxable',
                'institution': 'Treasury Direct',
                'holdings': [
                    {'ticker': 'IBOND', 'shares': Decimal('108000.00')},
                ],
            },
            {
                'name': 'WF Cash Account',
                'account_subtype': 'Taxable',
                'institution': 'Wells Fargo',
                'holdings': [
                    {'ticker': 'CASH', 'shares': Decimal('150000.00')},
                ],
            },
            {
                'name': 'WF S&P',
                'account_subtype': 'Taxable',
                'institution': 'Wells Fargo',
                'holdings': [
                    {'ticker': 'VOO', 'shares': Decimal('95.48')},
                ],
            },
            {
                'name': 'ML Brokerage',
                'account_subtype': 'Taxable',
                'institution': 'Merrill Lynch',
                'holdings': [
                    {'ticker': 'VOO', 'shares': Decimal('656.00')},
                    {'ticker': 'VEA', 'shares': Decimal('5698.00')},
                    {'ticker': 'VGSH', 'shares': Decimal('3026.00')},
                    {'ticker': 'VIG', 'shares': Decimal('665.00')},
                    {'ticker': 'VTV', 'shares': Decimal('750.00')},
                    {'ticker': 'VWO', 'shares': Decimal('2540.00')},
                    {'ticker': 'VGIT', 'shares': Decimal('968.00')},
                    {'ticker': 'CASH', 'shares': Decimal('0.00')},
                ],
            },
            {
                'name': 'CB IRA',
                'account_subtype': 'Trad. IRA',
                'institution': 'Charles Schwab',
                'holdings': [
                    {'ticker': 'VGSH', 'shares': Decimal('2078.00')},
                    {'ticker': 'VTI', 'shares': Decimal('288.00')},
                    {'ticker': 'VNQ', 'shares': Decimal('941.00')},
                    {'ticker': 'VEA', 'shares': Decimal('606.00')},
                    {'ticker': 'VGIT', 'shares': Decimal('288.00')},
                    {'ticker': 'CASH', 'shares': Decimal('2659.00')},
                ],
            },
            {
                'name': 'EB IRA',
                'account_subtype': 'Trad. IRA',
                'institution': 'Charles Schwab',
                'holdings': [
                    {'ticker': 'VGSH', 'shares': Decimal('1535.00')},
                    {'ticker': 'VNQ', 'shares': Decimal('713.00')},
                    {'ticker': 'VTI', 'shares': Decimal('217.00')},
                    {'ticker': 'VEA', 'shares': Decimal('455.00')},
                    {'ticker': 'VGIT', 'shares': Decimal('217.00')},
                    {'ticker': 'CASH', 'shares': Decimal('1722.00')},
                ],
            },
            {
                'name': 'CB Roth IRA',
                'account_subtype': 'Roth IRA',
                'institution': 'Charles Schwab',
                'holdings': [
                    {'ticker': 'VTI', 'shares': Decimal('85.00')},
                    {'ticker': 'USRT', 'shares': Decimal('448.00')},
                    {'ticker': 'VEA', 'shares': Decimal('267.00')},
                    {'ticker': 'VGSH', 'shares': Decimal('256.00')},
                    {'ticker': 'VWO', 'shares': Decimal('104.00')},
                    {'ticker': 'VIG', 'shares': Decimal('25.00')},
                    {'ticker': 'VGIT', 'shares': Decimal('85.00')},
                    {'ticker': 'VTV', 'shares': Decimal('27.00')},
                    {'ticker': 'CASH', 'shares': Decimal('640.00')},
                ],
            },
            {
                'name': 'EB Roth IRA',
                'account_subtype': 'Roth IRA',
                'institution': 'Charles Schwab',
                'holdings': [
                    {'ticker': 'VTI', 'shares': Decimal('78.00')},
                    {'ticker': 'USRT', 'shares': Decimal('401.00')},
                    {'ticker': 'VEA', 'shares': Decimal('245.00')},
                    {'ticker': 'VGSH', 'shares': Decimal('236.00')},
                    {'ticker': 'VWO', 'shares': Decimal('96.00')},
                    {'ticker': 'VIG', 'shares': Decimal('23.00')},
                    {'ticker': 'VTV', 'shares': Decimal('25.00')},
                    {'ticker': 'VGIT', 'shares': Decimal('78.00')},
                    {'ticker': 'CASH', 'shares': Decimal('622.00')},
                ],
            },
        ]

        for account_data in account_rows:
            account_type, tax_treatment = self._map_account_fields(account_data['account_subtype'])
            account_obj, _ = Account.objects.update_or_create(
                user=admin_user,
                name=account_data['name'],
                defaults={
                    'account_type': account_type,
                    'institution': account_data['institution'],
                    'tax_treatment': tax_treatment,
                }
            )

            for holding_data in account_data['holdings']:
                security = Security.objects.get(ticker=holding_data['ticker'])
                Holding.objects.update_or_create(
                    account=account_obj,
                    security=security,
                    defaults={'shares': holding_data['shares']}
                )

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))

    def _map_account_fields(self, account_subtype: str) -> tuple[str, str]:
        subtype = account_subtype.lower()
        if 'roth' in subtype:
            return 'ROTH_IRA', 'TAX_FREE'
        if 'trad' in subtype:
            return 'TRADITIONAL_IRA', 'TAX_DEFERRED'
        return 'TAXABLE', 'TAXABLE'

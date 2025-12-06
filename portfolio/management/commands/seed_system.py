import os
from decimal import Decimal
from typing import Any, TypedDict

from django.core.management.base import BaseCommand

from portfolio.models import (
    AccountGroup,
    AccountType,
    AssetCategory,
    AssetClass,
    Institution,
    Security,
)


class AccountGroupSeed(TypedDict):
    name: str
    sort_order: int


class AccountTypeSeed(TypedDict):
    code: str
    label: str
    group: str
    tax_treatment: str


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


class InstitutionSeed(TypedDict):
    name: str


class Command(BaseCommand):
    help = 'Seeds the database with system reference data (Asset Classes, Account Types, etc.)'

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write('Seeding System Data...')

        # 1. Account Groups
        # Note: Renaming 'Cash / Deposit' to 'Deposit' as per user intent implyied by 'Deposit' usage
        groups: list[AccountGroupSeed] = [
            {'name': 'Investments', 'sort_order': 1},
            {'name': 'Retirement', 'sort_order': 2},
            {'name': 'Deposit', 'sort_order': 3}, 
        ]
        
        group_objects = {}
        for g_data in groups:
             obj, created = AccountGroup.objects.get_or_create(
                 name=g_data['name'], 
                 defaults={'sort_order': g_data['sort_order']}
             )
             group_objects[obj.name] = obj
             if created: self.stdout.write(self.style.SUCCESS(f'Created Group: {obj.name}'))

        # 2. Account Types
        types: list[AccountTypeSeed] = [
             {'code': 'TAXABLE', 'label': 'Taxable Brokerage', 'group': 'Investments', 'tax_treatment': 'TAXABLE'},
             {'code': 'TRADITIONAL_IRA', 'label': 'Traditional IRA', 'group': 'Retirement', 'tax_treatment': 'TAX_DEFERRED'},
             {'code': 'ROTH_IRA', 'label': 'Roth IRA', 'group': 'Retirement', 'tax_treatment': 'TAX_FREE'},
             {'code': 'DEPOSIT', 'label': 'Deposit Account', 'group': 'Deposit', 'tax_treatment': 'TAXABLE'},
        ]
        
        for t_data in types:
             obj, created = AccountType.objects.update_or_create(
                 code=t_data['code'],
                 defaults={
                     'label': t_data['label'],
                     'group': group_objects[t_data['group']],
                     'tax_treatment': t_data['tax_treatment']
                 }
             )
             if created: self.stdout.write(self.style.SUCCESS(f'Created Account Type: {obj.label}'))

        # 3. Asset Categories (hierarchical)
        categories: list[CategorySeed] = [
            {'code': 'EQUITIES', 'label': 'Equities', 'parent': None, 'sort_order': 1},
            {'code': 'US_EQUITIES', 'label': 'US Equities', 'parent': 'EQUITIES', 'sort_order': 2},
            {'code': 'INTERNATIONAL_EQUITIES', 'label': 'International Equities', 'parent': 'EQUITIES', 'sort_order': 3},
            {'code': 'FIXED_INCOME', 'label': 'Fixed Income', 'parent': None, 'sort_order': 4},
            {'code': 'REAL_ASSETS', 'label': 'Real Assets', 'parent': None, 'sort_order': 5},
            {'code': 'CASH', 'label': 'Cash', 'parent': None, 'sort_order': 6},
        ]

        category_objects = {}
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

        # 4. Asset Classes
        asset_classes: list[AssetClassSeed] = [
            {'name': 'US Equities', 'category': 'US_EQUITIES', 'expected_return': Decimal('0.08')},
            {'name': 'US Real Estate', 'category': 'US_EQUITIES', 'expected_return': Decimal('0.06')},
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

        # 5. Securities
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
            {'ticker': 'VXUS', 'name': 'Vanguard Total International Stock ETF', 'asset_class': 'International Developed Equities'}, # Needed for test user
            {'ticker': 'BND', 'name': 'Vanguard Total Bond Market ETF', 'asset_class': 'US Intermediate-term Treasuries'}, # Needed for test user
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
        
        # 6. Institutions
        institutions: list[InstitutionSeed] = [
            {'name': 'Bank of America'},
            {'name': 'Merrill Lynch'},
            {'name': 'Wealthfront'},
            {'name': 'Wells Fargo'},
            {'name': 'JP Morgan Chase'},
            {'name': 'Charles Schwab'},
            {'name': 'Citibank'},
            {'name': 'Treasury Direct'},
            {'name': 'Vanguard'},
        ]

        for inst_data in institutions:
            obj, created = Institution.objects.get_or_create(name=inst_data['name'])
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created Institution: {obj.name}'))

        self.stdout.write(self.style.SUCCESS('System Data seeded successfully!'))

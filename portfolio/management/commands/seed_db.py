import os
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from portfolio.models import AssetClass, Security


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

        # Asset Classes
        asset_classes = [
            {'name': 'US Equities', 'expected_return': Decimal('0.08')},
            {'name': 'US Real Estate', 'expected_return': Decimal('0.06')},
            {'name': 'US Dividend Equities', 'expected_return': Decimal('0.07')},
            {'name': 'US Value Equities', 'expected_return': Decimal('0.075')},
            {'name': 'International Developed Equities', 'expected_return': Decimal('0.07')},
            {'name': 'International Emerging Equities', 'expected_return': Decimal('0.09')},
            {'name': 'US Short-term Treasuries', 'expected_return': Decimal('0.03')},
            {'name': 'US Intermediate-term Treasuries', 'expected_return': Decimal('0.04')},
        ]

        for ac_data in asset_classes:
            ac_obj, created = AssetClass.objects.get_or_create(
                name=ac_data['name'],
                defaults={'expected_return': ac_data['expected_return']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created Asset Class: {ac_obj.name}'))
            else:
                self.stdout.write(f'Asset Class already exists: {ac_obj.name}')

        # Securities
        securities = [
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

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))

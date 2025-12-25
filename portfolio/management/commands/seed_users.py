import os
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portfolio.models import (
    Account,
    AccountType,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    AssetClass,
    Holding,
    Institution,
    Portfolio,
    Security,
)
from users.models import CustomUser

User = get_user_model()

SECURITY_PRICES = {
    "IBOND": Decimal("1.00"),
    "VOO": Decimal("622.01"),
    "VTI": Decimal("333.25"),
    "VNQ": Decimal("88.93"),
    "VTV": Decimal("190.86"),
    "VIG": Decimal("219.37"),
    "VEA": Decimal("62.51"),
    "VWO": Decimal("53.58"),
    "VGSH": Decimal("58.69"),
    "VGIT": Decimal("60.02"),
    "CASH": Decimal("1.00"),
    "USRT": Decimal("50.00"),
    "BND": Decimal("75.00"),
    "VXUS": Decimal("60.00"),
}


class Command(BaseCommand):
    help = "Seeds the database with User portfolios (Admin and Test User)"

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Seeding User Data...")

        # Helper to lookup types efficiently
        type_objects = {t.code: t for t in AccountType.objects.all()}

        # ---------------------------
        # 1. Admin / Superuser
        # ---------------------------
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "admin")

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username, email, password)
            self.stdout.write(self.style.SUCCESS(f"Created superuser: {username}"))
        else:
            self.stdout.write(f"Superuser already exists: {username}")

        admin_user = User.objects.get(username=username)

        # Cleanup admin portfolios (user requested clean admin)
        admin_portfolio, _ = Portfolio.objects.update_or_create(
            user=admin_user,
            name="Main Portfolio",
            defaults={},
        )

        # ---------------------------
        # 2. Test User
        # ---------------------------
        test_username = "testuser"
        test_email = "test@example.com"
        test_password = "testpassword"

        if not User.objects.filter(username=test_username).exists():
            User.objects.create_user(test_username, test_email, test_password)
            self.stdout.write(self.style.SUCCESS(f"Created test user: {test_username}"))
        else:
            self.stdout.write(f"Test user already exists: {test_username}")

        test_user = User.objects.get(username=test_username)

        test_portfolio, _ = Portfolio.objects.update_or_create(
            user=test_user,
            name="Main Portfolio",
            defaults={},
        )

        # Realistic "Main" Accounts (previously under admin)
        main_accounts: list[dict[str, Any]] = [
            {
                "name": "Treasury Direct",
                "account_subtype": "DEPOSIT",
                "institution": "Treasury Direct",
                "holdings": [{"ticker": "IBOND", "shares": Decimal("108000.00")}],
            },
            {
                "name": "WF Cash Account",
                "account_subtype": "DEPOSIT",
                "institution": "Wealthfront",
                "holdings": [{"ticker": "CASH", "shares": Decimal("150000.00")}],
            },
            {
                "name": "WF S&P",
                "account_subtype": "TAXABLE",
                "institution": "Wealthfront",
                "holdings": [{"ticker": "VOO", "shares": Decimal("95.48")}],
            },
            {
                "name": "ML Brokerage",
                "account_subtype": "TAXABLE",
                "institution": "Merrill Lynch",
                "holdings": [
                    {"ticker": "VOO", "shares": Decimal("656.00")},
                    {"ticker": "VEA", "shares": Decimal("5698.00")},
                    {"ticker": "VGSH", "shares": Decimal("3026.00")},
                    {"ticker": "VIG", "shares": Decimal("665.00")},
                    {"ticker": "VTV", "shares": Decimal("750.00")},
                    {"ticker": "VWO", "shares": Decimal("2540.00")},
                    {"ticker": "VGIT", "shares": Decimal("968.00")},
                    {"ticker": "CASH", "shares": Decimal("0.00")},
                ],
            },
            {
                "name": "CB IRA",
                "account_subtype": "TRADITIONAL_IRA",
                "institution": "Merrill Lynch",
                "holdings": [
                    {"ticker": "VGSH", "shares": Decimal("2078.00")},
                    {"ticker": "VTI", "shares": Decimal("288.00")},
                    {"ticker": "VNQ", "shares": Decimal("941.00")},
                    {"ticker": "VEA", "shares": Decimal("606.00")},
                    {"ticker": "VGIT", "shares": Decimal("288.00")},
                    {"ticker": "CASH", "shares": Decimal("2659.00")},
                ],
            },
            {
                "name": "EB IRA",
                "account_subtype": "TRADITIONAL_IRA",
                "institution": "Merrill Lynch",
                "holdings": [
                    {"ticker": "VGSH", "shares": Decimal("1535.00")},
                    {"ticker": "VNQ", "shares": Decimal("713.00")},
                    {"ticker": "VTI", "shares": Decimal("217.00")},
                    {"ticker": "VEA", "shares": Decimal("455.00")},
                    {"ticker": "VGIT", "shares": Decimal("217.00")},
                    {"ticker": "CASH", "shares": Decimal("1722.00")},
                ],
            },
            {
                "name": "CB Roth IRA",
                "account_subtype": "ROTH_IRA",
                "institution": "Merrill Lynch",
                "holdings": [
                    {"ticker": "VTI", "shares": Decimal("85.00")},
                    {"ticker": "USRT", "shares": Decimal("448.00")},
                    {"ticker": "VEA", "shares": Decimal("267.00")},
                    {"ticker": "VGSH", "shares": Decimal("256.00")},
                    {"ticker": "VWO", "shares": Decimal("104.00")},
                    {"ticker": "VIG", "shares": Decimal("25.00")},
                    {"ticker": "VGIT", "shares": Decimal("85.00")},
                    {"ticker": "VTV", "shares": Decimal("27.00")},
                    {"ticker": "CASH", "shares": Decimal("640.00")},
                ],
            },
            {
                "name": "EB Roth IRA",
                "account_subtype": "ROTH_IRA",
                "institution": "Merrill Lynch",
                "holdings": [
                    {"ticker": "VTI", "shares": Decimal("78.00")},
                    {"ticker": "USRT", "shares": Decimal("401.00")},
                    {"ticker": "VEA", "shares": Decimal("245.00")},
                    {"ticker": "VGSH", "shares": Decimal("236.00")},
                    {"ticker": "VWO", "shares": Decimal("96.00")},
                    {"ticker": "VIG", "shares": Decimal("23.00")},
                    {"ticker": "VTV", "shares": Decimal("25.00")},
                    {"ticker": "VGIT", "shares": Decimal("78.00")},
                    {"ticker": "CASH", "shares": Decimal("622.00")},
                ],
            },
        ]

        # Realistic Strategies
        main_strategies: list[dict[str, Any]] = [
            {
                "name": "Portfolio Default",
                "is_portfolio_default": True,
                "allocations": {
                    "US Equities": Decimal("27.5"),
                    "US Real Estate": Decimal("10.0"),
                    "US Quality Equities": Decimal("5.0"),
                    "US Small Cap Value Equities": Decimal("5.0"),
                    "International Developed Equities": Decimal("17.5"),
                    "International Emerging Equities": Decimal("5.0"),
                    "US Treasuries - Short": Decimal("15.0"),
                    "US Treasuries - Intermediate": Decimal("5.0"),
                    "Inflation Adjusted Bond": Decimal("5.0"),
                },
            },
            {
                "name": "Taxable Strategy",
                "account_type_code": "TAXABLE",
                "allocations": {
                    "US Equities": Decimal("30.0"),
                    "US Small Cap Value Equities": Decimal("10.0"),
                    "US Quality Equities": Decimal("10.0"),
                    "International Developed Equities": Decimal("25.0"),
                    "International Emerging Equities": Decimal("10.0"),
                    "US Treasuries - Short": Decimal("10.0"),
                    "US Treasuries - Intermediate": Decimal("5.0"),
                },
            },
            {
                "name": "Traditional IRA Strategy",
                "account_type_code": "TRADITIONAL_IRA",
                "allocations": {
                    "US Equities": Decimal("25.0"),
                    "US Real Estate": Decimal("30.0"),
                    "International Developed Equities": Decimal("10.0"),
                    "US Treasuries - Short": Decimal("30.0"),
                    "US Treasuries - Intermediate": Decimal("5.0"),
                },
            },
            {
                "name": "Roth IRA Strategy",
                "account_type_code": "ROTH_IRA",
                "allocations": {
                    "US Equities": Decimal("25.0"),
                    "US Real Estate": Decimal("25.0"),
                    "US Small Cap Value Equities": Decimal("5.0"),
                    "US Quality Equities": Decimal("5.0"),
                    "International Developed Equities": Decimal("15.0"),
                    "International Emerging Equities": Decimal("5.0"),
                    "US Treasuries - Short": Decimal("15.0"),
                    "US Treasuries - Intermediate": Decimal("5.0"),
                },
            },
            {
                "name": "Deposit Strategy",
                "account_type_code": "DEPOSIT",
                "allocations": {
                    "Inflation Adjusted Bond": Decimal("50.0"),
                },
            },
        ]

        self.seed_user_portfolio(admin_user, admin_portfolio, main_accounts, type_objects)
        self.seed_user_targets(admin_user, admin_portfolio, main_strategies, type_objects)

        self.stdout.write(self.style.SUCCESS("User Data seeded successfully!"))

    def seed_user_portfolio(
        self,
        user: CustomUser,
        portfolio: Portfolio,
        accounts_data: list[dict],
        type_objects: dict,
    ) -> None:
        for account_data in accounts_data:
            institution, _ = Institution.objects.get_or_create(name=account_data["institution"])

            # Helper logic to handle casing or direct code match
            subtype = account_data["account_subtype"]
            # Simple mapping if not redundant
            if subtype.lower() == "taxable":
                subtype = "TAXABLE"
            elif "trad" in subtype.lower():
                subtype = "TRADITIONAL_IRA"
            elif "roth" in subtype.lower():
                subtype = "ROTH_IRA"

            account_type = type_objects.get(subtype)
            if not account_type:
                self.stdout.write(self.style.ERROR(f"Unknown Account Type code: {subtype}"))
                continue

            account_obj, _ = Account.objects.update_or_create(
                user=user,
                name=account_data["name"],
                defaults={
                    "portfolio": portfolio,
                    "account_type": account_type,
                    "institution": institution,
                },
            )

            for holding_data in account_data["holdings"]:
                ticker = holding_data.get("ticker")
                try:
                    security = Security.objects.get(ticker=ticker)
                except Security.DoesNotExist:
                    fallback = holding_data.get("fallback_ticker")
                    if fallback:
                        try:
                            security = Security.objects.get(ticker=fallback)
                        except Security.DoesNotExist:
                            continue
                    else:
                        continue

                Holding.objects.update_or_create(
                    account=account_obj,
                    security=security,
                    defaults={
                        "shares": holding_data["shares"],
                        "current_price": SECURITY_PRICES.get(ticker, Decimal("100.00")),
                    },
                )

    def seed_user_targets(
        self,
        user: CustomUser,
        portfolio: Portfolio,
        strategies_data: list[dict],
        type_objects: dict,
    ) -> None:
        ac_map = {ac.name: ac.id for ac in AssetClass.objects.all()}

        for strategy_data in strategies_data:
            name = strategy_data["name"]
            allocations_dict = {}
            for ac_name, pct in strategy_data["allocations"].items():
                ac_id = ac_map.get(ac_name)
                if ac_id:
                    asset_class = AssetClass.objects.get(id=ac_id)
                    if not asset_class.is_cash():
                        allocations_dict[ac_id] = Decimal(str(pct))

            strategy, _ = AllocationStrategy.objects.update_or_create(
                user=user,
                name=name,
                defaults={"description": f"Seeded strategy: {name}"},
            )
            # Domain model handles cash remainder and persistence
            strategy.save_allocations(allocations_dict)

            if strategy_data.get("is_portfolio_default"):
                portfolio.allocation_strategy = strategy
                portfolio.save(update_fields=["allocation_strategy"])

            at_code = strategy_data.get("account_type_code")
            if at_code:
                account_type = type_objects.get(at_code)
                if account_type:
                    AccountTypeStrategyAssignment.objects.update_or_create(
                        user=user,
                        account_type=account_type,
                        defaults={"allocation_strategy": strategy},
                    )

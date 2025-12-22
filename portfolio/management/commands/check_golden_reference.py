from decimal import Decimal
from typing import Any, TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

import pandas as pd

from portfolio.domain.portfolio import Portfolio as DomainPortfolio
from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    Holding,
    Security,
    TargetAllocation,
)
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


class Command(BaseCommand, PortfolioTestMixin):
    help = "Visually spot check the golden reference holdings and calculations."

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            self.stdout.write(self.style.SUCCESS("Setting up golden reference data..."))

            # 1. Setup User and Portfolio
            username = "golden_ref_user"
            User.objects.filter(username=username).delete()
            self.user = User.objects.create_user(username=username, password="password")
            self.create_portfolio(user=self.user, name="Golden Reference Portfolio")

            # 2. Setup System Data (Institutions, Asset Classes, etc.)
            self.setup_system_data()

            # 3. Replicate the Golden Reference Scenario Setup
            self.setup_golden_reference_scenario()

            # 4. Load Domain Portfolio and Display Results
            domain_portfolio = DomainPortfolio.load_for_user(self.user)

            self.stdout.write("\n" + "=" * 80)
            self.stdout.write("GOLDEN REFERENCE PORTFOLIO STATUS")
            self.stdout.write("=" * 80 + "\n")

            self.display_portfolio_totals(domain_portfolio)
            self.display_account_breakdown(domain_portfolio)
            self.display_asset_class_breakdown(domain_portfolio)

            # Cleanup - deleting the user will cascade delete the portfolio and holdings
            self.user.delete()
            self.stdout.write(self.style.SUCCESS("\nDone. Golden reference data cleaned up."))

    def setup_golden_reference_scenario(self) -> None:
        """Replicates the setup from test_golden_reference.py"""
        # Fetch all required securities first
        self.sec_ibond = Security.objects.get(ticker="IBOND")
        self.sec_voo = Security.objects.get(ticker="VOO")
        self.sec_vti = Security.objects.get(ticker="VTI")
        self.sec_vnq = Security.objects.get(ticker="VNQ")
        self.sec_vtv = Security.objects.get(ticker="VTV")
        self.sec_avuv = Security.objects.get(ticker="AVUV")
        self.sec_jqua = Security.objects.get(ticker="JQUA")
        self.sec_vig = Security.objects.get(ticker="VIG")
        self.sec_vea = Security.objects.get(ticker="VEA")
        self.sec_vwo = Security.objects.get(ticker="VWO")
        self.sec_vgsh = Security.objects.get(ticker="VGSH")
        self.sec_vgit = Security.objects.get(ticker="VGIT")
        self.sec_cash = Security.objects.get(ticker="CASH")

        # --- Strategies ---
        self.strategy_inflation_only = AllocationStrategy.objects.create(
            user=self.user, name="Inflation Bonds Only"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_inflation_only,
            asset_class=self.asset_class_inflation_bond,
            target_percent=Decimal("100.00"),
        )

        self.strategy_sp_only = AllocationStrategy.objects.create(user=self.user, name="S&P Only")
        TargetAllocation.objects.create(
            strategy=self.strategy_sp_only,
            asset_class=self.asset_class_us_equities,
            target_percent=Decimal("100.00"),
        )

        self.strategy_taxable = AllocationStrategy.objects.create(
            user=self.user, name="Taxable Strategy"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_taxable,
            asset_class=self.asset_class_us_equities,
            target_percent=Decimal("30.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_taxable,
            asset_class=self.asset_class_intl_developed,
            target_percent=Decimal("25.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_taxable,
            asset_class=self.asset_class_intl_emerging,
            target_percent=Decimal("10.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_taxable,
            asset_class=self.asset_class_treasuries_short,
            target_percent=Decimal("10.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_taxable,
            asset_class=self.asset_class_treasuries_intermediate,
            target_percent=Decimal("5.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_taxable,
            asset_class=self.asset_class_cash,
            target_percent=Decimal("20.00"),
        )

        self.strategy_tax_deferred = AllocationStrategy.objects.create(
            user=self.user, name="Tax Deferred Strategy"
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_tax_deferred,
            asset_class=self.asset_class_us_equities,
            target_percent=Decimal("25.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_tax_deferred,
            asset_class=self.asset_class_us_real_estate,
            target_percent=Decimal("30.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_tax_deferred,
            asset_class=self.asset_class_intl_developed,
            target_percent=Decimal("10.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_tax_deferred,
            asset_class=self.asset_class_treasuries_short,
            target_percent=Decimal("30.00"),
        )
        TargetAllocation.objects.create(
            strategy=self.strategy_tax_deferred,
            asset_class=self.asset_class_treasuries_intermediate,
            target_percent=Decimal("5.00"),
        )

        AccountTypeStrategyAssignment.objects.create(
            user=self.user,
            account_type=self.type_taxable,
            allocation_strategy=self.strategy_taxable,
        )
        AccountTypeStrategyAssignment.objects.create(
            user=self.user,
            account_type=self.type_traditional_ira,
            allocation_strategy=self.strategy_tax_deferred,
        )

        # --- Accounts & Holdings ---
        # 1. Treasury Direct
        acc_treasury = Account.objects.create(
            user=self.user,
            name="Treasury Direct",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
            allocation_strategy=self.strategy_inflation_only,
        )
        Holding.objects.create(
            account=acc_treasury,
            security=self.sec_ibond,
            shares=Decimal("108000.00"),
            current_price=Decimal("1.00"),
        )

        # 2. WF S&P
        acc_wf_sp = Account.objects.create(
            user=self.user,
            name="WF S&P",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
            allocation_strategy=self.strategy_sp_only,
        )
        Holding.objects.create(
            account=acc_wf_sp,
            security=self.sec_voo,
            shares=Decimal("70000.00") / Decimal("622.01"),
            current_price=Decimal("622.01"),
        )

        # 3. ML Brokerage
        acc_ml = Account.objects.create(
            user=self.user,
            name="ML Brokerage",
            portfolio=self.portfolio,
            account_type=self.type_taxable,
            institution=self.institution,
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_voo,
            shares=Decimal("656.00"),
            current_price=Decimal("622.01"),
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_vea,
            shares=Decimal("5698.00"),
            current_price=Decimal("62.51"),
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_vgsh,
            shares=Decimal("3026.00"),
            current_price=Decimal("58.69"),
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_vig,
            shares=Decimal("665.00"),
            current_price=Decimal("219.37"),
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_vtv,
            shares=Decimal("750.00"),
            current_price=Decimal("190.86"),
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_vwo,
            shares=Decimal("2540.00"),
            current_price=Decimal("53.58"),
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_vgit,
            shares=Decimal("968.00"),
            current_price=Decimal("60.02"),
        )
        Holding.objects.create(
            account=acc_ml,
            security=self.sec_cash,
            shares=Decimal("5.00"),
            current_price=Decimal("1.00"),
        )

        # 4. CB IRA
        acc_cb_ira = Account.objects.create(
            user=self.user,
            name="CB IRA",
            portfolio=self.portfolio,
            account_type=self.type_traditional_ira,
            institution=self.institution,
        )
        Holding.objects.create(
            account=acc_cb_ira,
            security=self.sec_vnq,
            shares=Decimal("1202.00"),
            current_price=Decimal("88.93"),
        )
        Holding.objects.create(
            account=acc_cb_ira,
            security=self.sec_vgsh,
            shares=Decimal("1731.00"),
            current_price=Decimal("58.69"),
        )
        Holding.objects.create(
            account=acc_cb_ira,
            security=self.sec_vti,
            shares=Decimal("288.00"),
            current_price=Decimal("333.25"),
        )
        Holding.objects.create(
            account=acc_cb_ira,
            security=self.sec_vea,
            shares=Decimal("606.00"),
            current_price=Decimal("62.51"),
        )
        Holding.objects.create(
            account=acc_cb_ira,
            security=self.sec_vgit,
            shares=Decimal("288.00"),
            current_price=Decimal("60.02"),
        )
        Holding.objects.create(
            account=acc_cb_ira,
            security=self.sec_cash,
            shares=Decimal("11.00"),
            current_price=Decimal("1.00"),
        )

    def display_portfolio_totals(self, portfolio: DomainPortfolio) -> None:
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"Total Portfolio Value: ${portfolio.total_value:,.2f}")
        )
        self.stdout.write("-" * 80)

    def display_account_breakdown(self, portfolio: DomainPortfolio) -> None:
        self.stdout.write(self.style.MIGRATE_LABEL("\nACCOUNT BREAKDOWN"))
        data = []
        for account in portfolio.accounts:
            data.append(
                {
                    "Account": account.name,
                    "Type": account.account_type.label,
                    "Value": f"${account.total_value():,.2f}",
                }
            )
        df = pd.DataFrame(data)
        self.stdout.write(df.to_string(index=False))

    def display_asset_class_breakdown(self, portfolio: DomainPortfolio) -> None:
        self.stdout.write(self.style.MIGRATE_LABEL("\nASSET CLASS ALLOCATION (FULL PORTFOLIO)"))

        from portfolio.services.targets import TargetAllocationService

        effective_allocs = TargetAllocationService.get_effective_allocations(self.user)
        variances = portfolio.variance_from_allocations(effective_allocs)

        by_ac = portfolio.value_by_asset_class()
        total = portfolio.total_value

        data = []
        for ac_name, current_val in by_ac.items():
            variance = variances.get(ac_name, Decimal("0.00"))
            target_val = current_val - variance

            current_pct = (current_val / total * 100) if total > 0 else 0
            target_pct = (target_val / total * 100) if total > 0 else 0

            data.append(
                {
                    "Asset Class": ac_name,
                    "Current ($)": float(current_val),
                    "Target ($)": float(target_val),
                    "Var ($)": float(variance),
                    "Cur %": float(current_pct),
                    "Tar %": float(target_pct),
                }
            )

        # Add any asset classes that HAVE a target but NO current holdings
        for ac_name, variance_neg in variances.items():
            if ac_name not in by_ac:
                target_val = -variance_neg
                variance = variance_neg
                target_pct = (target_val / total * 100) if total > 0 else 0

                data.append(
                    {
                        "Asset Class": ac_name,
                        "Current ($)": 0.0,
                        "Target ($)": float(target_val),
                        "Var ($)": float(variance),
                        "Cur %": 0.0,
                        "Tar %": float(target_pct),
                    }
                )

        df = pd.DataFrame(data)
        # Sort by Current ($) descending
        df = df.sort_values(by="Current ($)", ascending=False)

        # Format the numbers for display
        format_mapping = {
            "Current ($)": "${:,.2f}".format,
            "Target ($)": "${:,.2f}".format,
            "Var ($)": "${:,.2f}".format,
            "Cur %": "{:.1f}%".format,
            "Tar %": "{:.1f}%".format,
        }

        for col, fmt in format_mapping.items():
            df[col] = df[col].apply(fmt)

        self.stdout.write(df.to_string(index=False))

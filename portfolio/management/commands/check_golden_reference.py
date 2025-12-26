from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

import pandas as pd

from portfolio.domain.allocation import AssetAllocation
from portfolio.domain.portfolio import Portfolio as DomainPortfolio
from portfolio.models import (
    Account,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    Holding,
    Security,
    TargetAllocation,
)
from portfolio.services.allocation_calculations import AllocationCalculationEngine
from portfolio.services.allocation_presentation import AllocationPresentationFormatter
from portfolio.tests.base import PortfolioTestMixin

User = get_user_model()


class Command(BaseCommand, PortfolioTestMixin):
    help = "Visually spot check the golden reference holdings and calculations."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(self.style.SUCCESS("Checking portfolio status for testuser..."))

        # 1. Setup User
        username = "testuser"
        try:
            self.user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User {username} does not exist. Run seed_db first.")
            )
            return

        # 2. Setup System Data (Institutions, Asset Classes, etc.)
        self.setup_system_data()

        # 3. Load Domain Portfolio and Display Results
        domain_portfolio = DomainPortfolio.load_for_user(self.user)

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"PORTFOLIO STATUS: {username}")
        self.stdout.write("=" * 80 + "\n")

        self.display_portfolio_totals(domain_portfolio)
        self.display_account_type_breakdown(domain_portfolio)
        self.display_account_breakdown(domain_portfolio)
        self.display_asset_class_breakdown(domain_portfolio)
        self.display_account_variances(domain_portfolio)
        self.display_detailed_holdings(domain_portfolio)

        # 4. New Engine Validation
        self.display_new_engine_results(self.user)

        self.stdout.write(self.style.SUCCESS("\nVerification complete."))

    def _get_effective_allocations_as_domain_objects(
        self, user: Any
    ) -> dict[int, list[AssetAllocation]]:
        """Adapter to convert Engine's map format to Domain Objects expected by Portfolio domain."""
        engine = AllocationCalculationEngine()
        target_map = engine.get_effective_target_map(user)

        result = {}
        for acc_id, targets in target_map.items():
            result[acc_id] = [
                AssetAllocation(asset_class_name=ac_name, target_pct=pct)
                for ac_name, pct in targets.items()
            ]
        return result

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
            asset_class=self.asset_class_tips,
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
            asset_class=self.asset_class_treasuries_interm,
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
            asset_class=self.asset_class_treasuries_interm,
            target_percent=Decimal("5.00"),
        )

        AccountTypeStrategyAssignment.objects.create(
            user=self.user,
            account_type=self.type_taxable,
            allocation_strategy=self.strategy_taxable,
        )
        AccountTypeStrategyAssignment.objects.create(
            user=self.user,
            account_type=self.type_trad,
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
            account_type=self.type_trad,
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

    def format_df_for_display(self, df: pd.DataFrame, left_align_cols: list[str]) -> str:
        """Helper to ensure left alignment and spacing for terminal output."""
        # Ensure identifying columns are left-aligned by manual padding
        for col in left_align_cols:
            if col in df.columns:
                col_max_len = max(df[col].astype(str).str.len().max(), len(col))
                df[col] = df[col].astype(str).str.ljust(col_max_len)

        return df.to_string(index=False, justify="left", col_space=4)

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
        self.stdout.write(self.format_df_for_display(df, ["Account", "Type"]))

    def display_asset_class_breakdown(self, portfolio: DomainPortfolio) -> None:
        self.stdout.write(self.style.MIGRATE_LABEL("\nASSET CLASS ALLOCATION (FULL PORTFOLIO)"))

        effective_allocs = self._get_effective_allocations_as_domain_objects(self.user)
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

        self.stdout.write(self.format_df_for_display(df, ["Asset Class"]))

    def display_account_type_breakdown(self, portfolio: DomainPortfolio) -> None:
        self.stdout.write(self.style.MIGRATE_LABEL("\nACCOUNT TYPE BREAKDOWN"))
        by_type = portfolio.value_by_account_type()
        total = portfolio.total_value

        data = []
        for type_code, value in by_type.items():
            data.append(
                {
                    "Type": type_code,
                    "Value": float(value),
                    "Pct": float(value / total * 100) if total > 0 else 0,
                }
            )

        if not data:
            self.stdout.write("No account type data.")
            return

        df = pd.DataFrame(data)
        df["Value"] = df["Value"].apply("${:,.2f}".format)
        df["Pct"] = df["Pct"].apply("{:.1f}%".format)
        self.stdout.write(self.format_df_for_display(df, ["Type", "Pct"]))

    def display_account_variances(self, portfolio: DomainPortfolio) -> None:
        self.stdout.write(self.style.MIGRATE_LABEL("\nACCOUNT-LEVEL VARIANCES"))

        effective_allocs = self._get_effective_allocations_as_domain_objects(self.user)

        for account in portfolio.accounts:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nAccount: {account.name}"))
            account_total = account.total_value()
            holdings_by_ac = account.holdings_by_asset_class()
            allocations = effective_allocs.get(account.id, [])

            data = []
            # Calculate for all asset classes involved in this account (current or target)
            involved_acs = set(holdings_by_ac.keys()) | {a.asset_class_name for a in allocations}

            for ac_name in involved_acs:
                current_val = holdings_by_ac.get(ac_name, Decimal("0.00"))
                target_pct = Decimal("0.00")
                for a in allocations:
                    if a.asset_class_name == ac_name:
                        target_pct = a.target_pct
                        break

                target_val = (account_total * target_pct / 100).quantize(Decimal("0.01"))
                variance = current_val - target_val

                data.append(
                    {
                        "Asset Class": ac_name,
                        "Current ($)": float(current_val),
                        "Target ($)": float(target_val),
                        "Var ($)": float(variance),
                        "Cur %": float(current_val / account_total * 100)
                        if account_total > 0
                        else 0,
                        "Tar %": float(target_pct),
                    }
                )

            if data:
                df = pd.DataFrame(data)
                df = df.sort_values(by="Current ($)", ascending=False)
                format_mapping = {
                    "Current ($)": "${:,.2f}".format,
                    "Target ($)": "${:,.2f}".format,
                    "Var ($)": "${:,.2f}".format,
                    "Cur %": "{:.1f}%".format,
                    "Tar %": "{:.1f}%".format,
                }
                for col, fmt in format_mapping.items():
                    df[col] = df[col].apply(fmt)
                self.stdout.write(self.format_df_for_display(df, ["Asset Class"]))
            else:
                self.stdout.write("No holdings or targets for this account.")

    def display_detailed_holdings(self, portfolio: DomainPortfolio) -> None:
        self.stdout.write(self.style.MIGRATE_LABEL("\nDETAILED HOLDINGS BY ACCOUNT"))

        for account in portfolio.accounts:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nAccount: {account.name}"))
            holdings = account.holdings.select_related("security__asset_class").all()

            data = []
            for h in holdings:
                data.append(
                    {
                        "Ticker": h.security.ticker,
                        "Asset Class": h.security.asset_class.name,
                        "Shares": f"{h.shares:,.4f}",
                        "Price": f"${h.current_price:,.2f}" if h.current_price else "N/A",
                        "Market Value": float(h.market_value),
                    }
                )

            if data:
                df = pd.DataFrame(data)
                df = df.sort_values(by="Market Value", ascending=False)
                df["Market Value"] = df["Market Value"].apply("${:,.2f}".format)
                self.stdout.write(self.format_df_for_display(df, ["Ticker", "Asset Class"]))
            else:
                self.stdout.write("No holdings in this account.")

    def display_new_engine_results(self, user: Any) -> None:
        """Display the output of the new AllocationCalculationEngine and Formatter."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("NEW ENGINE (PANDAS) VALIDATION SECTION")
        self.stdout.write("=" * 80 + "\n")

        engine = AllocationCalculationEngine()
        formatter = AllocationPresentationFormatter()

        # Step 1: Build numeric DataFrame
        df = engine.build_presentation_dataframe(user=user)

        if df.empty:
            self.stdout.write(self.style.WARNING("Engine returned empty DataFrame."))
            return

        # Step 2: Aggregate at all levels
        aggregated = engine.aggregate_presentation_levels(df)

        # Step 3: Format for display
        _, accounts_by_type = engine._get_account_metadata(user)
        strategies_data = engine._get_target_strategies(user)

        rows = formatter.format_presentation_rows(
            aggregated_data=aggregated,
            accounts_by_type=accounts_by_type,
            target_strategies=strategies_data,
            mode="percent",
        )

        self.stdout.write(self.style.MIGRATE_LABEL("REFACTORED ALLOCATION TABLE (PERCENT MODE)"))

        # Convert the formatted rows into a flat list for a DataFrame
        # For simplicity, we just show Asset Class Name and Portfolio Pcts
        table_data = []
        for row in rows:
            table_data.append(
                {
                    "Level": row["row_type"],
                    "Asset Class": row["asset_class_name"],
                    "Current": row["portfolio"]["current"],
                    "Target": row["portfolio"]["target"],
                    "Var": row["portfolio"]["variance"],
                }
            )

        df_presentation = pd.DataFrame(table_data)
        self.stdout.write(self.format_df_for_display(df_presentation, ["Level", "Asset Class"]))

        # Also show Holdings Detail from Engine
        effective_targets_map = engine.get_effective_target_map(user)

        # Build raw holdings DF (similar to HoldingsView)
        holdings_qs = Holding.objects.filter(account__user=user).select_related(
            "account", "security__asset_class"
        )
        raw_holdings = []
        for h in holdings_qs:
            raw_holdings.append(
                {
                    "Account_ID": h.account_id,
                    "Asset_Class": h.security.asset_class.name,
                    "Security": h.security.ticker,
                    "Value": float(h.market_value),
                    "Shares": float(h.shares),
                    "Price": float(h.current_price) if h.current_price else 0.0,
                }
            )
        holdings_df = pd.DataFrame(raw_holdings)

        detail_df = engine.calculate_holdings_detail(holdings_df, effective_targets_map)

        self.stdout.write(self.style.MIGRATE_LABEL("\nENGINE HOLDINGS DETAIL VALIDATION"))
        detail_display = detail_df[
            ["Ticker", "Asset_Class", "Value", "Target_Value", "Variance"]
        ].copy()
        detail_display["Value"] = detail_display["Value"].apply("${:,.2f}".format)
        detail_display["Target_Value"] = detail_display["Target_Value"].apply("${:,.2f}".format)
        detail_display["Variance"] = detail_display["Variance"].apply("${:,.2f}".format)

        self.stdout.write(self.format_df_for_display(detail_display, ["Ticker", "Asset_Class"]))

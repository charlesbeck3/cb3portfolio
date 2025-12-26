from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models

import pandas as pd

if TYPE_CHECKING:
    from portfolio.models.strategies import AllocationStrategy

from portfolio.managers import AccountManager


class Institution(models.Model):
    """Financial institution (e.g., Vanguard, Fidelity)."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AccountGroup(models.Model):
    """Group of accounts (e.g., Retirement, Investments, Deposit Accounts)."""

    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.name


class AccountType(models.Model):
    """Specific type of account (e.g., Roth IRA, Taxable)."""

    TAX_TREATMENT_CHOICES = [
        ("TAX_FREE", "Tax Free"),
        ("TAX_DEFERRED", "Tax Deferred"),
        ("TAXABLE", "Taxable"),
    ]

    # ============================================================================
    # Constants
    # ============================================================================

    # Tax treatment choices
    TAX_FREE = "TAX_FREE"
    """Tax-free growth and withdrawals (e.g., Roth IRA)."""

    TAX_DEFERRED = "TAX_DEFERRED"
    """Tax-deferred growth with taxable withdrawals (e.g., Traditional IRA, 401k)."""

    TAXABLE = "TAXABLE"
    """Taxable account with annual tax on gains and dividends."""

    # Redefined choices using constants
    TAX_TREATMENT_CHOICES = [
        (TAX_FREE, "Tax Free"),
        (TAX_DEFERRED, "Tax Deferred"),
        (TAXABLE, "Taxable"),
    ]

    # Common account type codes (for frequently referenced types)
    CODE_ROTH_IRA = "ROTH_IRA"
    CODE_TRADITIONAL_IRA = "TRADITIONAL_IRA"
    CODE_401K = "401K"
    CODE_ROTH_401K = "ROTH_401K"
    CODE_TAXABLE = "TAXABLE"
    CODE_DEPOSIT = "DEPOSIT"
    CODE_HSA = "HSA"

    # Valid account type codes for validation
    VALID_CODES = {
        CODE_ROTH_IRA,
        CODE_TRADITIONAL_IRA,
        CODE_401K,
        CODE_ROTH_401K,
        CODE_TAXABLE,
        CODE_DEPOSIT,
        CODE_HSA,
    }

    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    group = models.ForeignKey(AccountGroup, on_delete=models.PROTECT, related_name="account_types")
    tax_treatment = models.CharField(max_length=20, choices=TAX_TREATMENT_CHOICES)

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        """Validate account type constraints."""
        from django.core.exceptions import ValidationError

        super().clean()

        if self.code and self.code not in self.VALID_CODES:
            raise ValidationError(
                {
                    "code": f"Invalid account type code '{self.code}'. "
                    f"Must be one of: {', '.join(sorted(self.VALID_CODES))}"
                }
            )

    # ============================================================================
    # Instance Methods
    # ============================================================================

    def is_tax_advantaged(self) -> bool:
        """
        Check if this account type has tax advantages.

        Returns:
            True if tax-free or tax-deferred, False if taxable
        """
        return self.tax_treatment in (self.TAX_FREE, self.TAX_DEFERRED)

    def is_tax_free(self) -> bool:
        """Check if this is a tax-free account type (e.g., Roth IRA)."""
        return self.tax_treatment == self.TAX_FREE

    def is_tax_deferred(self) -> bool:
        """Check if this is a tax-deferred account type (e.g., Traditional IRA)."""
        return self.tax_treatment == self.TAX_DEFERRED

    def is_taxable(self) -> bool:
        """Check if this is a taxable account type."""
        return self.tax_treatment == self.TAXABLE

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert all accounts of this type to DataFrame.

        Returns:
            DataFrame with one row per account of this type.
        """
        accounts = self.accounts.all()

        if not accounts:
            return pd.DataFrame()

        # Get DataFrame for each account and concatenate
        dfs = [account.to_dataframe() for account in accounts]

        if not dfs:
            return pd.DataFrame()

        df = pd.concat(dfs, axis=0)
        # Sort just in case concating mixed up order slightly or for consistency
        return df.sort_index(axis=0).sort_index(axis=1)


class Account(models.Model):
    """Investment account (e.g., Roth IRA, Taxable)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts"
    )
    name = models.CharField(max_length=100)
    portfolio = models.ForeignKey("Portfolio", on_delete=models.CASCADE, related_name="accounts")
    account_type = models.ForeignKey(AccountType, on_delete=models.PROTECT, related_name="accounts")
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="accounts")
    allocation_strategy = models.ForeignKey(
        "AllocationStrategy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_assignments",
    )

    objects = AccountManager()

    def __str__(self) -> str:
        return f"{self.name} ({self.user.username})"

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert account holdings to DataFrame.
        """
        holdings = self.holdings.select_related("security__asset_class__category").all()

        # Build column dict
        data = {}
        for holding in holdings:
            col_key = (
                holding.security.asset_class.name,
                holding.security.asset_class.category.label,
                holding.security.ticker,
            )
            value = float(holding.market_value)
            data[col_key] = value

        if not data:
            return pd.DataFrame(
                index=pd.MultiIndex.from_tuples(
                    [], names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"]
                ),
                columns=pd.MultiIndex.from_tuples(
                    [], names=["Asset_Class", "Asset_Category", "Security"]
                ),
            )

        # Single-row DataFrame
        df = pd.DataFrame([data])

        # Set MultiIndex for columns
        df.columns = pd.MultiIndex.from_tuples(
            df.columns,
            names=["Asset_Class", "Asset_Category", "Security"],
        )

        # Set index to account hierarchy with ID
        row_key = (self.account_type.label, self.account_type.group.name, self.name, self.id)
        df.index = pd.MultiIndex.from_tuples(
            [row_key], names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"]
        )

        df = df.fillna(0.0).sort_index(axis=1)

        return df

    @property
    def is_tax_advantaged(self) -> bool:
        """Returns True if account has tax-advantaged treatment."""
        return self.account_type.is_tax_advantaged()

    @property
    def tax_treatment(self) -> str:
        return self.account_type.tax_treatment

    def get_effective_allocation_strategy(self) -> AllocationStrategy | None:
        if self.allocation_strategy_id:
            return self.allocation_strategy

        # Late import to avoid circular dependency
        from portfolio.models.strategies import AccountTypeStrategyAssignment

        assignment = (
            AccountTypeStrategyAssignment.objects.select_related("allocation_strategy")
            .filter(user_id=self.user_id, account_type_id=self.account_type_id)
            .first()
        )
        if assignment is not None:
            return assignment.allocation_strategy

        return self.portfolio.allocation_strategy

    def get_target_allocations_by_name(self) -> dict[str, Decimal]:
        """
        Get effective target allocations for this account keyed by asset class name.

        Follows hierarchy: Account override -> Account Type -> Portfolio default.

        Returns:
            Dict of {asset_class_name: target_percent}
            Empty dict if no strategy assigned.

        Example:
            >>> account.get_target_allocations_by_name()
            {'US Equities': Decimal('60.00'), 'Bonds': Decimal('30.00'), 'Cash': Decimal('10.00')}
        """
        strategy = self.get_effective_allocation_strategy()
        if not strategy:
            return {}
        return strategy.get_allocations_by_name()

    # ===== Aggregate Methods =====

    def total_value(self) -> Decimal:
        """Calculate total market value of all holdings in this account."""

        total = Decimal("0.00")
        for holding in self.holdings.all():
            total += holding.market_value
        return total

    def holdings_by_asset_class(self) -> dict[str, Decimal]:
        """Group holdings by asset class name and sum market values."""

        result: dict[str, Decimal] = {}
        for holding in self.holdings.select_related("security__asset_class").all():
            ac_name = holding.security.asset_class.name
            result[ac_name] = result.get(ac_name, Decimal("0.00")) + holding.market_value
        return result

    def calculate_deviation(self, targets: dict[str, Decimal]) -> Decimal:
        """Calculate sum of absolute deviations from target allocation.

        Args:
            targets: Mapping of asset class name to target percentage (0-100).
        """

        from portfolio.domain.allocation import AssetAllocation

        allocations = [
            AssetAllocation(asset_class_name=name, target_pct=pct) for name, pct in targets.items()
        ]
        return self.calculate_deviation_from_allocations(allocations)

    def calculate_deviation_from_allocations(self, allocations: list[Any]) -> Decimal:
        """Calculate sum of absolute deviations from target allocation.

        Args:
            allocations: List of AssetAllocation domain objects.
        """
        account_total = self.total_value()
        holdings_by_ac = self.holdings_by_asset_class()

        # Build targets dict from allocations
        targets_by_name = {a.asset_class_name: a for a in allocations}

        total_deviation = Decimal("0.00")
        all_asset_classes = set(targets_by_name.keys()) | set(holdings_by_ac.keys())

        for ac_name in all_asset_classes:
            actual = holdings_by_ac.get(ac_name, Decimal("0.00"))
            alloc = targets_by_name.get(ac_name)
            target_value = alloc.target_value_for(account_total) if alloc else Decimal("0.00")
            total_deviation += abs(actual - target_value)

        return total_deviation

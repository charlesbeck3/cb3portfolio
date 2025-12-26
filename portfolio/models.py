from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings

import pandas as pd

if TYPE_CHECKING:
    from portfolio.domain.allocation import AssetAllocation
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from portfolio.managers import AccountManager, HoldingManager, TargetAllocationManager


class AssetClassCategory(models.Model):
    """Hierarchical asset category that can be grouped under a parent category."""

    code = models.CharField(max_length=50, primary_key=True)
    label = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "label"]
        verbose_name = "Asset Class Category"
        verbose_name_plural = "Asset Class Categories"

    def __str__(self) -> str:
        return self.label


class AssetClass(models.Model):
    """Broad category of investments (e.g., US Stocks, Bonds)."""

    name = models.CharField(
        max_length=100, unique=True, help_text="Asset class name (e.g., 'US Large Cap Stocks')"
    )
    category = models.ForeignKey(
        AssetClassCategory,
        on_delete=models.PROTECT,
        related_name="asset_classes",
        to_field="code",
        db_column="category",
        help_text="Broad asset category",
    )
    expected_return = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Expected annual return (%)",
    )

    # ============================================================================
    # Constants
    # ============================================================================

    # Special asset class names
    CASH_NAME = "Cash"
    """
    The standard name for the Cash asset class.

    Cash is handled specially throughout the application:
    - Automatically calculated by AllocationStrategy.save_allocations()
    - Excluded from user input collection in strategy forms
    - Acts as the "plug" to ensure allocations sum to 100%
    """

    class Meta:
        verbose_name_plural = "Asset Classes"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    # ============================================================================
    # Instance Methods
    # ============================================================================

    def is_cash(self) -> bool:
        """
        Check if this asset class is Cash.

        Returns:
            True if this is the Cash asset class, False otherwise

        Example:
            >>> asset_class = AssetClass.objects.get(name="Cash")
            >>> asset_class.is_cash()
            True
        """
        return self.name == self.CASH_NAME

    # ============================================================================
    # Class Methods
    # ============================================================================

    @classmethod
    def get_cash(cls) -> AssetClass | None:
        """
        Get the Cash asset class from database (cached).

        This method uses caching to avoid repeated database queries for the
        same Cash asset class within a single process lifetime.

        Returns:
            AssetClass instance for Cash, or None if not found

        Example:
            >>> cash = AssetClass.get_cash()
            >>> if cash:
            ...     print(f"Cash ID: {cash.id}")
        """
        from functools import lru_cache

        @lru_cache(maxsize=1)
        def _get_cash() -> AssetClass | None:
            try:
                return cls.objects.get(name=cls.CASH_NAME)
            except cls.DoesNotExist:
                return None

        return _get_cash()


class Portfolio(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
    )
    name = models.CharField(max_length=100)
    allocation_strategy = models.ForeignKey(
        "AllocationStrategy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portfolio_assignments",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="unique_portfolio_name_per_user"),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.user.username})"

    def clean(self) -> None:  # noqa: DJ012
        """Validate portfolio invariants."""
        from django.core.exceptions import ValidationError

        super().clean()

        # Only validate allocation strategy if one is assigned
        if self.allocation_strategy_id:
            strategy = self.allocation_strategy
            if strategy is not None:
                is_valid, error_msg = strategy.validate_allocations()
                if not is_valid:
                    raise ValidationError({"allocation_strategy": error_msg})

    def save(self, *args: Any, **kwargs: Any) -> None:  # noqa: DJ012
        """Save portfolio with validation."""
        # Only validate on updates (when pk exists)
        if self.pk:
            self.full_clean()
        super().save(*args, **kwargs)

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert portfolio holdings to MultiIndex DataFrame.

        Returns:
            DataFrame where:
            - Rows: MultiIndex(Account_Type, Account_Category, Account_Name, Account_ID)
            - Cols: MultiIndex(Asset_Class, Asset_Category, Security)
            - Values: Dollar amounts (shares * current_price)
        """
        # Fetch all holdings for this portfolio
        holdings = (
            Holding.objects.filter(account__portfolio=self)
            .select_related(
                "account__account_type__group",
                "security__asset_class__category",
            )
            .all()
        )

        # Build nested dict structure for DataFrame
        # data[row_key][col_key] = value
        data: dict[tuple[Any, ...], dict[tuple[Any, ...], float]] = defaultdict(
            lambda: defaultdict(float)
        )

        for holding in holdings:
            # Row: Account hierarchy
            row_key = (
                holding.account.account_type.label,  # e.g., "Taxable"
                holding.account.account_type.group.name,  # e.g., "Brokerage"
                holding.account.name,  # e.g., "Merrill Lynch"
                holding.account.id,  # Include ID for precise mapping
            )

            # Column: Asset hierarchy
            col_key = (
                holding.security.asset_class.name,  # e.g., "Equities"
                holding.security.asset_class.category.label,  # e.g., "US Large Cap"
                holding.security.ticker,  # e.g., "VTI"
            )

            # Value: market value
            value = float(holding.market_value)
            data[row_key][col_key] = value

        if not data:
            # Empty portfolio - return empty DataFrame with correct structure
            return pd.DataFrame(
                index=pd.MultiIndex.from_tuples(
                    [], names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"]
                ),
                columns=pd.MultiIndex.from_tuples(
                    [], names=["Asset_Class", "Asset_Category", "Security"]
                ),
            )

        # Convert nested dict to DataFrame
        df = pd.DataFrame.from_dict(
            {row_key: dict(col_dict) for row_key, col_dict in data.items()},
            orient="index",
        )

        # Set MultiIndex for rows
        df.index = pd.MultiIndex.from_tuples(
            df.index,
            names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"],
        )

        # Set MultiIndex for columns
        df.columns = pd.MultiIndex.from_tuples(
            df.columns,
            names=["Asset_Class", "Asset_Category", "Security"],
        )

        # Fill NaN with 0 (accounts don't hold every security)
        df = df.fillna(0.0)

        # Sort for consistent ordering
        df = df.sort_index(axis=0).sort_index(axis=1)

        return df


class AllocationStrategy(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="allocation_strategies",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    # ============================================================================
    # Constants
    # ============================================================================

    # Allocation percentage constraints
    TOTAL_ALLOCATION_PCT = Decimal("100.00")
    """Total allocation must always equal 100%."""

    ALLOCATION_TOLERANCE = Decimal("0.001")
    """
    Tolerance for allocation validation (0.001%).

    Used to account for rounding errors in financial calculations.
    Allocations within this tolerance of 100% are considered valid.
    """

    MIN_ALLOCATION_PCT = Decimal("0.00")
    """Minimum allocation percentage for any asset class."""

    MAX_ALLOCATION_PCT = Decimal("100.00")
    """Maximum allocation percentage for any asset class."""

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_allocation_strategy_name_per_user",
            ),
        ]
        ordering = ["name"]
        verbose_name = "Allocation Strategy"
        verbose_name_plural = "Allocation Strategies"

    def __str__(self) -> str:
        return self.name

    def save_allocations(self, allocations: dict[int, Decimal]) -> None:
        """
        Save target allocations for this strategy.

        Handles cash allocation flexibly:
        - If cash is provided: Validates that all allocations sum to exactly 100%
        - If cash is omitted: Automatically calculates cash as the plug (100% - sum)

        Args:
            allocations: Dict of asset_class_id -> target_percent
                        May include or exclude Cash asset class

        Raises:
            ValueError: If allocations sum to != 100% (when cash provided)
                        If allocations sum to > 100% (when cash omitted)
                        If final allocations don't sum to exactly 100% (data integrity)

        Examples:
            # Explicit cash (must sum to exactly 100%)
            strategy.save_allocations({
                stocks_id: Decimal("60.00"),
                bonds_id: Decimal("30.00"),
                cash_id: Decimal("10.00")
            })

            # Implicit cash (auto-calculated as plug)
            strategy.save_allocations({
                stocks_id: Decimal("60.00"),
                bonds_id: Decimal("30.00")
            })  # Cash will be 10%
        """
        from django.db import transaction

        # Get Cash asset class
        cash_ac = AssetClass.get_cash()
        if not cash_ac:
            raise ValueError("Cash asset class must exist")

        cash_id = cash_ac.id

        # Check if user explicitly provided cash allocation
        cash_provided = cash_id in allocations

        # Calculate total
        total = sum(allocations.values())

        # Prepare final allocations dict
        final_allocations: dict[int, Decimal] = {}

        if cash_provided:
            # User specified cash explicitly - must sum to exactly 100%
            if abs(total - self.TOTAL_ALLOCATION_PCT) > self.ALLOCATION_TOLERANCE:
                raise ValueError(
                    f"Allocations sum to {total}%, expected exactly {self.TOTAL_ALLOCATION_PCT}% "
                    f"when Cash is explicitly provided"
                )
            # Use provided allocations as-is
            final_allocations = allocations
        else:
            # User omitted cash - calculate as plug using dedicated method
            if total > self.TOTAL_ALLOCATION_PCT + self.ALLOCATION_TOLERANCE:
                raise ValueError(f"Non-cash allocations sum to {total}%, which exceeds 100%")

            # Calculate cash using dedicated method
            cash_percent = self.calculate_cash_allocation(allocations)
            final_allocations = allocations.copy()

            # Only add cash if it's non-zero
            if cash_percent > Decimal("0.00"):
                final_allocations[cash_id] = cash_percent

        # DEFENSIVE VALIDATION: Verify final allocations sum to exactly 100%
        # This catches rounding errors, logic bugs, or any other issues
        # before persisting to database
        is_valid, error_msg = self.validate_allocations(final_allocations)
        if not is_valid:
            # This should never happen if logic is correct
            # If it does, it indicates a bug that must be fixed
            raise ValueError(
                f"Data integrity error: {error_msg}. "
                f"This indicates a bug in allocation calculation logic. "
                f"Allocations: {final_allocations}"
            )

        # Save to database
        with transaction.atomic():
            # Clear existing allocations
            self.target_allocations.all().delete()

            # Create all allocations (only non-zero values)
            for asset_class_id, target_percent in final_allocations.items():
                if target_percent > Decimal("0.00"):
                    TargetAllocation.objects.create(
                        strategy=self,
                        asset_class_id=asset_class_id,
                        target_percent=target_percent,
                    )

    def calculate_cash_allocation(self, non_cash_allocations: dict[int, Decimal]) -> Decimal:
        """
        Calculate cash allocation as the remainder to reach 100%.

        Separated into its own method for:
        - Explicit business rule documentation
        - Easier unit testing
        - Single source of truth for cash calculation logic

        Args:
            non_cash_allocations: Dict of {asset_class_id: target_percent}
                                  excluding cash

        Returns:
            Cash allocation percentage (100% - sum of non_cash)
            Will be Decimal("0.00") if non_cash allocations sum to 100%

        Examples:
            >>> strategy.calculate_cash_allocation({1: Decimal("60.00"), 2: Decimal("30.00")})
            Decimal('10.00')

            >>> strategy.calculate_cash_allocation({1: Decimal("100.00")})
            Decimal('0.00')
        """
        total = sum(non_cash_allocations.values())
        cash_percent = self.TOTAL_ALLOCATION_PCT - total
        return cash_percent

    def get_allocations_dict(self) -> dict[int, Decimal]:
        """
        Get all target allocations as a dictionary.

        Returns:
            Dict of asset_class_id -> target_percent (includes Cash)
        """
        return {ta.asset_class_id: ta.target_percent for ta in self.target_allocations.all()}

    def get_allocations_by_name(self) -> dict[str, Decimal]:
        """
        Get all target allocations keyed by asset class name.

        Convenience method for when you need names instead of IDs
        (common in display/calculation logic).

        Returns:
            Dict of {asset_class_name: target_percent}
            Includes all allocations (including Cash).

        Example:
            >>> strategy.get_allocations_by_name()
            {'US Equities': Decimal('60.00'), 'Bonds': Decimal('30.00'), 'Cash': Decimal('10.00')}
        """
        return {
            ta.asset_class.name: ta.target_percent
            for ta in self.target_allocations.select_related("asset_class").all()
        }

    def validate_allocations(
        self,
        allocations: dict[int, Decimal] | None = None,
        tolerance: Decimal | None = None,
        allow_implicit_cash: bool = False,
    ) -> tuple[bool, str]:
        """
        Validate that allocations sum to 100% within tolerance.

        This helper method can be used to validate allocations before
        attempting to save them, allowing for graceful error handling
        in views or forms.

        Args:
            allocations: Optional dict of asset_class_id -> target_percent.
                        If None, validates existing allocations from database.
            tolerance: Optional acceptable deviation from 100%.
                       If None, uses self.ALLOCATION_TOLERANCE.
            allow_implicit_cash: If True, allows total to be <= 100% (assuming
                                cash will be added later).

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if allocations are valid
            - error_message: Description of validation error, or empty string if valid

        Example:
            >>> is_valid, error = strategy.validate_allocations(allocations)
            >>> if not is_valid:
            ...     return render(request, 'form.html', {'error': error})
        """
        if tolerance is None:
            tolerance = self.ALLOCATION_TOLERANCE

        if allocations is None:
            total = sum(ta.target_percent for ta in self.target_allocations.all())
        else:
            total = sum(allocations.values())

        if allow_implicit_cash:
            if total > self.TOTAL_ALLOCATION_PCT + tolerance:
                return False, f"Total allocation is {total}%, which exceeds 100% (±{tolerance}%)"
            return True, ""

        if abs(total - self.TOTAL_ALLOCATION_PCT) > tolerance:
            return False, (
                f"Total allocation is {total}%, must equal "
                f"{self.TOTAL_ALLOCATION_PCT}% (±{tolerance}%)"
            )

        return True, ""

    @property
    def cash_allocation(self) -> Decimal:
        """Get the cash allocation percentage."""
        cash_ac = AssetClass.get_cash()
        if not cash_ac:
            return Decimal("0.00")

        ta = self.target_allocations.filter(asset_class=cash_ac).first()
        return ta.target_percent if ta else Decimal("0.00")


class AccountTypeStrategyAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_type_strategy_assignments",
    )
    account_type = models.ForeignKey(
        "AccountType",
        on_delete=models.CASCADE,
        related_name="strategy_assignments",
    )
    allocation_strategy = models.ForeignKey(
        "AllocationStrategy",
        on_delete=models.CASCADE,
        related_name="account_type_assignments",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "account_type"],
                name="unique_account_type_strategy_assignment_per_user",
            ),
        ]
        ordering = ["account_type__label"]

    def __str__(self) -> str:
        return (
            f"{self.user.username} - {self.account_type.label} -> {self.allocation_strategy.name}"
        )


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
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="accounts")
    account_type = models.ForeignKey(AccountType, on_delete=models.PROTECT, related_name="accounts")
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="accounts")
    allocation_strategy = models.ForeignKey(
        AllocationStrategy,
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
            # Empty account
            # Match Portfolio structure partially or fully?
            # For consistent concatenation, we should match levels if possible,
            # but Account Type doesn't have ID level naturally.
            # However, Portfolio.to_dataframe (which calls this indirectly via AccountType?)
            # No, Portfolio iterates holdings directly.
            # AccountType calls Account.to_dataframe.

            # If AccountType concatenates these, they must have same Index Names.
            # Let's check AccountType.to_dataframe... it concats.
            # If we change Account.to_dataframe index, we must ensure consistency.

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
        # We need Type/Group info here to match Portfolio structure if we want consistency?
        # Actually Portfolio.to_dataframe constructs it itself.
        # AccountType.to_dataframe relies on Account.to_dataframe.
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

    def calculate_deviation_from_allocations(self, allocations: list[AssetAllocation]) -> Decimal:
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


class TargetAllocation(models.Model):
    strategy = models.ForeignKey(
        AllocationStrategy,
        on_delete=models.CASCADE,
        related_name="target_allocations",
    )
    asset_class = models.ForeignKey(AssetClass, on_delete=models.PROTECT)
    target_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    objects = TargetAllocationManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["strategy", "asset_class"],
                name="unique_target_allocation_per_strategy_asset_class",
            )
        ]
        ordering = ["strategy", "asset_class"]

    def __str__(self) -> str:
        return f"{self.strategy.name}: {self.asset_class.name} - {self.target_percent}%"

    def clean(self) -> None:
        """Validate allocation constraints."""
        from django.core.exceptions import ValidationError

        super().clean()

        if self.target_percent < 0:
            raise ValidationError({"target_percent": "Target percentage cannot be negative"})

        if self.target_percent > 100:
            raise ValidationError({"target_percent": "Target percentage cannot exceed 100%"})

    # ===== Domain Methods =====

    def target_value_for(self, account_total: Decimal) -> Decimal:
        """Calculate the target dollar amount for a given account total."""

        return (account_total * self.target_percent / Decimal("100")).quantize(Decimal("0.01"))

    def variance_for(self, current_value: Decimal, account_total: Decimal) -> Decimal:
        """Calculate variance between current and target values."""

        target_value = self.target_value_for(account_total)
        return current_value - target_value

    def variance_pct_for(self, current_value: Decimal, account_total: Decimal) -> Decimal:
        """Calculate variance as a percentage of account total."""

        if account_total == 0:
            return Decimal("0.00")
        target_value = self.target_value_for(account_total)
        return (current_value - target_value) / account_total * Decimal("100")

    @classmethod
    def validate_allocation_set(cls, allocations: list[TargetAllocation]) -> tuple[bool, str]:
        """Validate that a set of allocations does not exceed 100%."""

        total = sum((a.target_percent for a in allocations), Decimal("0.00"))
        if total > Decimal("100.00"):
            return False, f"Allocations sum to {total}%, which exceeds 100%"
        return True, ""


class Security(models.Model):
    """Individual investment security (e.g., VTI, BND)."""

    ticker = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    asset_class = models.ForeignKey(AssetClass, on_delete=models.PROTECT, related_name="securities")

    class Meta:
        ordering = ["ticker"]
        verbose_name_plural = "Securities"

    def __str__(self) -> str:
        return f"{self.ticker} - {self.name}"


class Holding(models.Model):
    """Current investment holding in an account."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="holdings")
    security = models.ForeignKey(Security, on_delete=models.PROTECT, related_name="holdings")
    shares = models.DecimalField(
        max_digits=20, decimal_places=8, validators=[MinValueValidator(Decimal("0"))]
    )
    as_of_date = models.DateField(auto_now=True)
    current_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        null=True,
        blank=True,
    )

    objects = HoldingManager()

    class Meta:
        ordering = ["account", "security"]
        unique_together = ["account", "security"]

    def __str__(self) -> str:
        return f"{self.security.ticker} in {self.account.name} ({self.shares} shares)"

    # ===== Domain Methods =====

    @property
    def market_value(self) -> Decimal:
        """Current market value of this holding.

        Returns 0.00 when no current price is set.
        """

        if self.current_price is None:
            return Decimal("0.00")
        return (self.shares * self.current_price).quantize(Decimal("0.01"))

    @property
    def has_price(self) -> bool:
        """Whether this holding has a current price set."""

        return self.current_price is not None

    def update_price(self, new_price: Decimal) -> None:
        """Update the holding's current price and persist the change."""

        self.current_price = new_price
        self.save(update_fields=["current_price"])

    def calculate_target_value(self, account_total: Decimal, target_pct: Decimal) -> Decimal:
        """Calculate target dollar value for this holding.

        Target percentage is expressed on a 0-100 scale.
        """

        return account_total * target_pct / Decimal("100")

    def calculate_variance(self, target_value: Decimal) -> Decimal:
        """Calculate variance from target (positive = overweight)."""

        return self.market_value - target_value


class RebalancingRecommendation(models.Model):
    """Recommended trade to rebalance portfolio."""

    ACTIONS = [
        ("BUY", "Buy"),
        ("SELL", "Sell"),
    ]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="recommendations")
    security = models.ForeignKey(Security, on_delete=models.CASCADE)
    action = models.CharField(max_length=4, choices=ACTIONS)
    shares = models.DecimalField(max_digits=15, decimal_places=4)
    estimated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.action} {self.shares} {self.security.ticker} in {self.account.name}"


@receiver([post_save, post_delete], sender=TargetAllocation)
def validate_strategy_allocations_on_change(
    sender: type[TargetAllocation], instance: TargetAllocation, **kwargs: Any
) -> None:
    """Validate strategy allocations after any allocation change."""
    if kwargs.get("raw", False):
        # Skip validation during fixture loading
        return

    # Validate the strategy's allocations
    strategy = instance.strategy
    is_valid, error_msg = strategy.validate_allocations()
    if not is_valid:
        # Log warning but don't raise - this allows gradual fixes
        # In production, you might want to raise ValidationError instead
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Strategy '{strategy.name}' has invalid allocations: {error_msg}")

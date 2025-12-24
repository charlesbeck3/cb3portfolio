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

    class Meta:
        verbose_name_plural = "Asset Classes"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


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
        cash_ac = AssetClass.objects.filter(name="Cash").first()
        if not cash_ac:
            raise ValueError("Cash asset class must exist")

        cash_id = cash_ac.id

        # Check if user explicitly provided cash allocation
        cash_provided = cash_id in allocations

        # Calculate total
        total = sum(allocations.values())

        if cash_provided:
            # User specified cash explicitly - must sum to exactly 100%
            if total != Decimal("100.00"):
                raise ValueError(
                    f"Allocations sum to {total}%, expected exactly 100% "
                    f"when Cash is explicitly provided"
                )
            # Use provided allocations as-is
            final_allocations = allocations
        else:
            # User omitted cash - calculate as plug
            if total > Decimal("100.00"):
                raise ValueError(
                    f"Non-cash allocations sum to {total}%, which exceeds 100%"
                )

            # Add calculated cash allocation
            cash_percent = Decimal("100.00") - total
            final_allocations = allocations.copy()

            # Only add cash if it's non-zero
            if cash_percent > Decimal("0.00"):
                final_allocations[cash_id] = cash_percent

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

    def validate_allocations(self) -> tuple[bool, str]:
        """
        Validate that allocations sum to 100%.

        Returns:
            Tuple of (is_valid, error_message)
        """
        total = sum(ta.target_percent for ta in self.target_allocations.all())

        if total == Decimal("100.00"):
            return True, ""

        return False, f"Allocations sum to {total}%, expected 100%"

    @property
    def cash_allocation(self) -> Decimal:
        """Get the cash allocation percentage."""
        cash_ac = AssetClass.objects.filter(name="Cash").first()
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

    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    group = models.ForeignKey(AccountGroup, on_delete=models.PROTECT, related_name="account_types")
    tax_treatment = models.CharField(max_length=20, choices=TAX_TREATMENT_CHOICES)

    def __str__(self) -> str:
        return self.label

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

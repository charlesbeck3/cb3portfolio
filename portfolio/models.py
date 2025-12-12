from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from portfolio.managers import AccountManager, HoldingManager, TargetAllocationManager


class AssetCategory(models.Model):
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
        verbose_name = "Asset Category"
        verbose_name_plural = "Asset Categories"

    def __str__(self) -> str:
        return self.label


class AssetClass(models.Model):
    """Broad category of investments (e.g., US Stocks, Bonds)."""

    name = models.CharField(
        max_length=100, unique=True, help_text="Asset class name (e.g., 'US Large Cap Stocks')"
    )
    category = models.ForeignKey(
        AssetCategory,
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


class Account(models.Model):
    """Investment account (e.g., Roth IRA, Taxable)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts"
    )
    name = models.CharField(max_length=100)
    account_type = models.ForeignKey(AccountType, on_delete=models.PROTECT, related_name="accounts")
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="accounts")

    objects = AccountManager()

    def __str__(self) -> str:
        return f"{self.name} ({self.user.username})"

    @property
    def tax_treatment(self) -> str:
        return self.account_type.tax_treatment

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

        account_total = self.total_value()
        holdings_by_ac = self.holdings_by_asset_class()

        total_deviation = Decimal("0.00")
        all_asset_classes = set(targets.keys()) | set(holdings_by_ac.keys())

        for ac_name in all_asset_classes:
            actual = holdings_by_ac.get(ac_name, Decimal("0.00"))
            target_pct = targets.get(ac_name, Decimal("0.00"))
            target_value = account_total * target_pct / Decimal("100")
            total_deviation += abs(actual - target_value)

        return total_deviation


class TargetAllocation(models.Model):
    """Target allocation for a specific account type and asset class."""

    account_type = models.ForeignKey(
        AccountType, on_delete=models.PROTECT, related_name="target_allocations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="target_allocations"
    )
    asset_class = models.ForeignKey(
        AssetClass, on_delete=models.PROTECT, related_name="target_allocations"
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="target_allocations",
        null=True,
        blank=True,
        help_text="Optional specific account override. If null, applies to the account type generally.",
    )
    target_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    objects = TargetAllocationManager()

    class Meta:
        constraints = [
            # Constraint for Default Type Allocation (account is null)
            models.UniqueConstraint(
                fields=["user", "account_type", "asset_class"],
                condition=models.Q(account__isnull=True),
                name="unique_default_target_allocation",
            ),
            # Constraint for Specific Account Override (account is not null)
            models.UniqueConstraint(
                fields=["user", "account", "asset_class"],
                condition=models.Q(account__isnull=False),
                name="unique_account_target_allocation",
            ),
        ]

    def __str__(self) -> str:
        if self.account:
            return f"{self.user.username} - {self.account.name} (Override) - {self.asset_class.name}: {self.target_pct}%"
        return f"{self.user.username} - {self.account_type} (Default) - {self.asset_class.name}: {self.target_pct}%"

    # ===== Domain Methods =====

    def target_value_for(self, account_total: Decimal) -> Decimal:
        """Calculate the target dollar amount for a given account total."""

        return account_total * self.target_pct / Decimal("100")

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
    def validate_allocation_set(cls, allocations: list["TargetAllocation"]) -> tuple[bool, str]:
        """Validate that a set of allocations does not exceed 100%."""

        total = sum((a.target_pct for a in allocations), Decimal("0.00"))
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
        max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0"))]
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
        return self.shares * self.current_price

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

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AssetCategory(models.Model):
    """Hierarchical asset category that can be grouped under a parent category."""

    code = models.CharField(max_length=50, primary_key=True)
    label = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        related_name='children',
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'label']
        verbose_name = "Asset Category"
        verbose_name_plural = "Asset Categories"

    def __str__(self) -> str:
        return self.label


class AssetClass(models.Model):
    """Broad category of investments (e.g., US Stocks, Bonds)."""

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Asset class name (e.g., 'US Large Cap Stocks')"
    )
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT,
        related_name='asset_classes',
        to_field='code',
        db_column='category',
        help_text="Broad asset category"
    )
    expected_return = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Expected annual return (%)"
    )

    class Meta:
        verbose_name_plural = "Asset Classes"
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

class Institution(models.Model):
    """Financial institution (e.g., Vanguard, Fidelity)."""
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class AccountGroup(models.Model):
    """Group of accounts (e.g., Retirement, Investments, Deposit Accounts)."""
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self) -> str:
        return self.name


class Account(models.Model):
    """Investment account (e.g., Roth IRA, Taxable)."""

    ACCOUNT_TYPES = [
        ('ROTH_IRA', 'Roth IRA'),
        ('TRADITIONAL_IRA', 'Traditional IRA'),
        ('401K', '401(k)'),
        ('TAXABLE', 'Taxable'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name='accounts')
    group = models.ForeignKey(AccountGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='accounts')

    def __str__(self) -> str:
        return f"{self.name} ({self.user.username})"

    @property
    def tax_treatment(self) -> str:
        if self.account_type == 'ROTH_IRA':
            return 'TAX_FREE'
        elif self.account_type in ('TRADITIONAL_IRA', '401K'):
            return 'TAX_DEFERRED'
        return 'TAXABLE'

class TargetAllocation(models.Model):
    """Target allocation for a specific account type and asset class."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='target_allocations')
    account_type = models.CharField(
        max_length=20,
        choices=Account.ACCOUNT_TYPES,
    )
    asset_class = models.ForeignKey(AssetClass, on_delete=models.CASCADE)
    target_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )

    class Meta:
        unique_together = ['user', 'account_type', 'asset_class']

    def __str__(self) -> str:
        return f"{self.get_account_type_display()} - {self.asset_class.name}: {self.target_pct}% ({self.user.username})"

class Security(models.Model):
    """Individual investment security (e.g., VTI, BND)."""

    ticker = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    asset_class = models.ForeignKey(AssetClass, on_delete=models.PROTECT, related_name='securities')

    class Meta:
        ordering = ['ticker']
        verbose_name_plural = "Securities"

    def __str__(self) -> str:
        return f"{self.ticker} - {self.name}"

class Holding(models.Model):
    """Current investment holding in an account."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='holdings')
    security = models.ForeignKey(Security, on_delete=models.PROTECT, related_name='holdings')
    shares = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))]
    )
    as_of_date = models.DateField(auto_now=True)
    current_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['account', 'security']
        unique_together = ['account', 'security']

    def __str__(self) -> str:
        return f"{self.security.ticker} in {self.account.name} ({self.shares} shares)"

class RebalancingRecommendation(models.Model):
    """Recommended trade to rebalance portfolio."""

    ACTIONS = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='recommendations')
    security = models.ForeignKey(Security, on_delete=models.CASCADE)
    action = models.CharField(max_length=4, choices=ACTIONS)
    shares = models.DecimalField(max_digits=15, decimal_places=4)
    estimated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.action} {self.shares} {self.security.ticker} in {self.account.name}"

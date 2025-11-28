from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AssetClass(models.Model):
    """Investment asset class (e.g., US Stocks, Bonds)."""

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Asset class name (e.g., 'US Large Cap Stocks')"
    )
    expected_return = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Expected annual return (%)"
    )

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Asset Classes"

    def __str__(self) -> str:
        return self.name

class Account(models.Model):
    """Investment account (e.g., Roth IRA, 401k)."""

    ACCOUNT_TYPES = [
        ('ROTH_IRA', 'Roth IRA'),
        ('TRADITIONAL_IRA', 'Traditional IRA'),
        ('401K', '401(k)'),
        ('TAXABLE', 'Taxable'),
    ]

    TAX_TREATMENTS = [
        ('TAX_FREE', 'Tax Free'),
        ('TAX_DEFERRED', 'Tax Deferred'),
        ('TAXABLE', 'Taxable'),
    ]

    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    institution = models.CharField(max_length=100)
    tax_treatment = models.CharField(max_length=20, choices=TAX_TREATMENTS)

    def __str__(self) -> str:
        return f"{self.name} ({self.get_account_type_display()})"

class TargetAllocation(models.Model):
    """Target allocation for an asset class within a specific account type."""

    account_type = models.CharField(
        max_length=20,
        choices=Account.ACCOUNT_TYPES,
        help_text="Account type this allocation applies to"
    )
    asset_class = models.ForeignKey(AssetClass, on_delete=models.CASCADE)
    target_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Target allocation percentage (0-100)"
    )

    class Meta:
        ordering = ['account_type', 'asset_class']
        unique_together = ['account_type', 'asset_class']
        verbose_name_plural = "Target Allocations"

    def __str__(self) -> str:
        return f"{self.get_account_type_display()} - {self.asset_class.name}: {self.target_pct}%"

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
    cost_basis = models.DecimalField(
        max_digits=15,
        decimal_places=2,
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

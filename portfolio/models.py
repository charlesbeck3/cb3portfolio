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
    target_allocation_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Target allocation percentage (0-100)"
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
        return f"{self.name} ({self.target_allocation_pct}%)"

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

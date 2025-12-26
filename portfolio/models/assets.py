from __future__ import annotations

from functools import lru_cache

from django.db import models


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

        @lru_cache(maxsize=1)
        def _get_cash() -> AssetClass | None:
            try:
                return cls.objects.get(name=cls.CASH_NAME)
            except cls.DoesNotExist:
                return None

        return _get_cash()

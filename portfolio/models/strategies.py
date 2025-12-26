from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction

from portfolio.managers import TargetAllocationManager
from portfolio.models.assets import AssetClass

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


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

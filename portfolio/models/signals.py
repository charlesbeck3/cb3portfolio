from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from portfolio.models.strategies import TargetAllocation

logger = logging.getLogger(__name__)


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
        logger.warning(f"Strategy '{strategy.name}' has invalid allocations: {error_msg}")

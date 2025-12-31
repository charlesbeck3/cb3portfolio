"""
Template tags for allocation display and formatting.

These tags handle presentation concerns that don't belong in the service layer.
"""

from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def variance_css_class(variance: float | Decimal | None) -> str:
    """
    Get CSS class for variance value (positive/negative coloring).

    This filter determines the visual styling based on the numeric sign
    of the variance. Positive variances (over target) are colored green,
    negative variances (under target) are colored red.

    Architectural Pattern:
    Engine (raw numeric) -> Filter (CSS class mapping) -> Template (display)

    Args:
        variance: Numeric variance value (float, Decimal, or None)

    Returns:
        CSS class string:
        - > 0 -> 'variance-positive'
        - < 0 -> 'variance-negative'
        - otherwise -> ''

    Example:
        <td class="{{ row.variance_pct|variance_css_class }}">
    """
    if variance is None:
        return ""

    try:
        if variance > 0:
            return "variance-positive"
        elif variance < 0:
            return "variance-negative"
    except (TypeError, ValueError):
        # Handle cases where variance might not be comparable
        return ""

    return ""

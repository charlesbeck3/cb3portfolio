"""
Template tags for allocation display and formatting.

These tags handle presentation concerns that don't belong in the service layer.
"""

from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def row_css_class(row_type: str) -> str:
    """
    Get CSS class for row type.

    Args:
        row_type: One of 'asset', 'subtotal', 'group_total', 'grand_total'

    Returns:
        CSS class name
    """
    css_map = {
        "asset": "",
        "subtotal": "subtotal",
        "group_total": "group-total",
        "grand_total": "grand-total",
    }
    return css_map.get(row_type, "")


@register.filter
def variance_css_class(variance: float | Decimal | str) -> str:
    """
    Get CSS class for variance value (positive/negative coloring).

    Args:
        variance: Numeric variance value

    Returns:
        CSS class for styling
    """
    if isinstance(variance, str):
        # Handle formatted strings like "+5.2%" or "($1,000)"
        variance = (
            variance.replace("$", "")
            .replace(",", "")
            .replace("%", "")
            .replace("(", "-")
            .replace(")", "")
            .strip()
        )
        try:
            variance = float(variance)
        except (ValueError, AttributeError):
            return ""

    if variance > 0:
        return "variance-positive"
    elif variance < 0:
        return "variance-negative"
    return ""

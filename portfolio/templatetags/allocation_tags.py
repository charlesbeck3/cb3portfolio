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


@register.filter
def accounting_format(value: Decimal | float | None, decimal_places: int = 2) -> str:
    """
    Format a number in accounting style (right-aligned, consistent decimals).

    Args:
        value: Numeric value to format
        decimal_places: Number of decimal places

    Returns:
        Formatted string
    """
    if value is None:
        return "-"

    if isinstance(value, str):
        return value

    return f"{value:,.{decimal_places}f}"


@register.filter
def accounting_percent(value: Decimal | float | None, decimal_places: int = 1) -> str:
    """
    Format a percentage in accounting style.

    Args:
        value: Percentage value (e.g., 5.5 for 5.5%)
        decimal_places: Number of decimal places

    Returns:
        Formatted string with % sign
    """
    if value is None:
        return "-"

    if isinstance(value, str):
        return value

    return f"{value:,.{decimal_places}f}%"

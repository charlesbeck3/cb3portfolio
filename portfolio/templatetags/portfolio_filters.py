from decimal import Decimal, InvalidOperation
from typing import Any

from django import template

register = template.Library()


@register.filter
def percentage_of(value: Any, total: Any) -> Decimal:
    """
    Calculate percentage of value / total.
    Usage: {{ value|percentage_of:total }}
    """
    try:
        val_d = Decimal(str(value))
        tot_d = Decimal(str(total))
        if tot_d == 0:
            return Decimal("0")
        return (val_d / tot_d) * Decimal("100")
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("0")


@register.filter
def money(value: Any, decimals: int = 0) -> str:
    """
    Format as $1,234 or ($1,234) for negatives.

    Args:
        decimals: Number of decimal places (default: 0)

    Examples:
        {{ 1234.56|money }}    -> $1,235
        {{ -1234.56|money }}   -> ($1,235)
        {{ 1234.56|money:2 }}  -> $1,234.56
    """
    try:
        val = float(value)
        is_neg = val < 0
        formatted = f"${abs(val):,.{decimals}f}"
        return f"({formatted})" if is_neg else formatted
    except (ValueError, TypeError):
        return str(value)


@register.filter
def percent(value: Any, decimals: int = 1) -> str:
    """
    Format as 12.5% or (12.5%) for negatives.

    Args:
        decimals: Number of decimal places (default: 1)

    Examples:
        {{ 12.5|percent }}     -> 12.5%
        {{ -12.5|percent }}    -> (12.5%)
        {{ 12.345|percent:2 }} -> 12.35%
    """
    try:
        val = float(value)
        is_neg = val < 0
        formatted = f"{abs(val):.{decimals}f}%"
        return f"({formatted})" if is_neg else formatted
    except (ValueError, TypeError):
        return str(value)


@register.filter
def number(value: Any, decimals: int = 0) -> str:
    """
    Format as 1,234 or (1,234) for negatives.

    Args:
        decimals: Number of decimal places (default: 0)

    Examples:
        {{ 1234.56|number }}   -> 1,235
        {{ -1234.56|number }}  -> (1,235)
        {{ 1234.56|number:2 }} -> 1,234.56
    """
    try:
        val = float(value)
        is_neg = val < 0
        formatted = f"{abs(val):,.{decimals}f}"
        return f"({formatted})" if is_neg else formatted
    except (ValueError, TypeError):
        return str(value)

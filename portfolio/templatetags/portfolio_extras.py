from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def get_item(dictionary: Mapping[Any, Any] | None, key: Any) -> Any:
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def percentage_of(value: Any, total: Any) -> Decimal:
    try:
        dec_value = Decimal(str(value))
        dec_total = Decimal(str(total))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')
    if dec_total == 0:
        return Decimal('0')
    return (dec_value / dec_total) * Decimal('100')


@register.filter
def subtract(value: Any, arg: Any) -> Decimal:
    """Subtract arg from value."""
    try:
        dec_value = Decimal(str(value))
        dec_arg = Decimal(str(arg))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')
    return dec_value - dec_arg


@register.filter
def accounting_amount(value: Any, decimals: int = 0) -> str:
    """Format value as accounting amount: (1,234) for negative."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return '-'

    is_negative = d < 0
    abs_val = abs(d)

    # Format number with commas and specified decimals
    formatted = f"{abs_val:,.{decimals}f}"

    if is_negative:
        return f"(${formatted})"

    # Add hidden parenthesis for alignment
    return mark_safe(f"${formatted}<span style='visibility: hidden;'>)</span>")


@register.filter
def accounting_percent(value: Any, decimals: int = 1) -> str:
    """Format value as accounting percent: (12.3%) for negative."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return '-'

    is_negative = d < 0
    abs_val = abs(d)

    formatted = f"{abs_val:.{decimals}f}"

    if is_negative:
        return f"({formatted}%)"

    # Add hidden parenthesis for alignment
    return mark_safe(f"{formatted}%<span style='visibility: hidden;'>)</span>")


@register.filter
def accounting_number(value: Any, decimals: int = 2) -> str:
    """Format value as accounting number: (123.45) for negative, no symbol."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return '-'

    is_negative = d < 0
    abs_val = abs(d)

    formatted = f"{abs_val:,.{decimals}f}"

    if is_negative:
        return f"({formatted})"

    # Add hidden parenthesis for alignment
    return mark_safe(f"{formatted}<span style='visibility: hidden;'>)</span>")

from decimal import Decimal, InvalidOperation
from typing import Any

from django import template
from django.utils.safestring import mark_safe

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


def _format_accounting(value: Any, decimals: int = 0, prefix: str = "", suffix: str = "") -> str:
    try:
        val_f = float(str(value))
    except (ValueError, TypeError):
        return "-"

    is_negative = val_f < 0
    abs_val = abs(val_f)

    # Format number with commas and specific decimals
    # {:,.2f} format
    fmt = f"{{:,.{decimals}f}}"
    formatted_num = fmt.format(abs_val)

    result = f"{prefix}{formatted_num}{suffix}"

    if is_negative:
        return f"({result})"
    else:
        # Use invisible parentheses for alignment
        return mark_safe(
            f'<span style="visibility: hidden">(</span>{result}<span style="visibility: hidden">)</span>'
        )


@register.filter
def accounting_amount(value: Any, decimals: int = 0) -> str:
    """
    Format currency in accounting style: (1,234.00) for negative, 1,234.00 for positive (aligned).
    """
    return _format_accounting(value, decimals, prefix="$")


@register.filter
def accounting_number(value: Any, decimals: int = 2) -> str:
    """
    Format number in accounting style: (1,234.00).
    """
    return _format_accounting(value, decimals)


@register.filter
def accounting_percent(value: Any, decimals: int = 1) -> str:
    """
    Format percent in accounting style: (12.5%).
    """
    return _format_accounting(value, decimals, suffix="%")

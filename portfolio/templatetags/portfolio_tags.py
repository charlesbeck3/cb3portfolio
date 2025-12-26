from typing import Any

from django import template

register = template.Library()


@register.filter
def currency(value: Any) -> Any:
    """Format a value as currency ($1,234.56)."""
    try:
        val = float(value)
        return f"${val:,.2f}"
    except (ValueError, TypeError):
        return value


@register.filter
def percentage(value: Any, decimals: int = 2) -> Any:
    """Format a value as percentage (12.35%)."""
    try:
        val = float(value)
        return f"{val:,.{decimals}f}%"
    except (ValueError, TypeError):
        return value


@register.filter
def variance_class(value: Any, threshold: float = 5) -> str:
    """Return CSS class based on variance magnitude."""
    try:
        val = float(value)
        if abs(val) > threshold:
            return "text-danger"
        return "text-success"
    except (ValueError, TypeError):
        return ""

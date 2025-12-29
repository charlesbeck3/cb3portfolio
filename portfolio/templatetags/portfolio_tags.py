from typing import Any

from django import template

register = template.Library()


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

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from django import template

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

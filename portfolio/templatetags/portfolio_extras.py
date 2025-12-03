from typing import Any, Mapping

from django import template

register = template.Library()

@register.filter
def get_item(dictionary: Mapping[Any, Any] | None, key: Any) -> Any:
    if dictionary is None:
        return None
    return dictionary.get(key)

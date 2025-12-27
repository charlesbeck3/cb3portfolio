"""
Type stubs and custom types for cb3portfolio.

This module provides type hints for Django models and custom types
to improve type checking without requiring full Django typing.
"""

from decimal import Decimal
from typing import Any, Protocol


class DjangoUser(Protocol):
    """Type stub for Django User model."""

    id: int
    username: str
    email: str
    is_authenticated: bool
    is_active: bool
    is_staff: bool
    is_superuser: bool


class AccountProtocol(Protocol):
    """Type protocol for Account model."""

    id: int
    name: str
    user: Any
    portfolio: Any
    account_type: Any

    def total_value(self) -> Decimal: ...
    def calculate_variance(self) -> float: ...

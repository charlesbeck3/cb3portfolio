"""Protocol definitions for allocation system components."""

from typing import Any, Protocol

import pandas as pd

from .types import TargetMap


class DataProvider(Protocol):
    """Protocol for data access layer."""

    def get_holdings_df(self, user: Any) -> pd.DataFrame:
        """Get holdings as long-format DataFrame."""
        ...

    def get_accounts_metadata(self, user: Any) -> tuple[list[dict], dict[int, list[dict]]]:
        """Get account metadata."""
        ...

    def get_asset_classes_df(self, user: Any) -> pd.DataFrame:
        """Get asset class metadata as DataFrame."""
        ...

    def get_targets_map(self, user: Any) -> TargetMap:
        """Get effective target allocations for all accounts."""
        ...


class Calculator(Protocol):
    """Protocol for calculation operations."""

    def calculate_allocations(self, holdings_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Calculate allocations at all hierarchy levels."""
        ...

    def aggregate_by_level(self, df: pd.DataFrame, group_by: str | list[str]) -> pd.DataFrame:
        """Universal aggregation method."""
        ...


class Formatter(Protocol):
    """Protocol for formatting operations."""

    def to_presentation_rows(self, df: pd.DataFrame, metadata: dict) -> list[dict]:
        """Transform DataFrame to presentation rows."""
        ...

    def to_holdings_rows(self, df: pd.DataFrame) -> list[dict]:
        """Transform DataFrame to holdings rows."""
        ...

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.conf import settings
from django.db import models

import pandas as pd

from portfolio.models.securities import Holding
from portfolio.models.strategies import AllocationStrategy


class Portfolio(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
    )
    name = models.CharField(max_length=100)
    allocation_strategy = models.ForeignKey(
        AllocationStrategy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portfolio_assignments",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="unique_portfolio_name_per_user"),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.user.username})"

    def clean(self) -> None:  # noqa: DJ012
        """Validate portfolio invariants."""
        from django.core.exceptions import ValidationError

        super().clean()

        # Only validate allocation strategy if one is assigned
        if self.allocation_strategy_id:
            strategy = self.allocation_strategy
            if strategy is not None:
                is_valid, error_msg = strategy.validate_allocations()
                if not is_valid:
                    raise ValidationError({"allocation_strategy": error_msg})

    def save(self, *args: Any, **kwargs: Any) -> None:  # noqa: DJ012
        """Save portfolio with validation."""
        # Only validate on updates (when pk exists)
        if self.pk:
            self.full_clean()
        super().save(*args, **kwargs)

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert portfolio holdings to MultiIndex DataFrame.

        Returns:
            DataFrame where:
            - Rows: MultiIndex(Account_Type, Account_Category, Account_Name, Account_ID)
            - Cols: MultiIndex(Asset_Class, Asset_Category, Security)
            - Values: Dollar amounts (shares * current_price)
        """
        # Fetch all holdings for this portfolio
        holdings = (
            Holding.objects.filter(account__portfolio=self)
            .select_related(
                "account__account_type__group",
                "security__asset_class__category",
            )
            .all()
        )

        # Build nested dict structure for DataFrame
        # data[row_key][col_key] = value
        data: dict[tuple[Any, ...], dict[tuple[Any, ...], float]] = defaultdict(
            lambda: defaultdict(float)
        )

        for holding in holdings:
            # Row: Account hierarchy
            row_key = (
                holding.account.account_type.label,  # e.g., "Taxable"
                holding.account.account_type.group.name,  # e.g., "Brokerage"
                holding.account.name,  # e.g., "Merrill Lynch"
                holding.account.id,  # Include ID for precise mapping
            )

            # Column: Asset hierarchy
            col_key = (
                holding.security.asset_class.name,  # e.g., "Equities"
                holding.security.asset_class.category.label,  # e.g., "US Large Cap"
                holding.security.ticker,  # e.g., "VTI"
            )

            # Value: market value
            value = float(holding.market_value)
            data[row_key][col_key] = value

        if not data:
            # Empty portfolio - return empty DataFrame with correct structure
            return pd.DataFrame(
                index=pd.MultiIndex.from_tuples(
                    [], names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"]
                ),
                columns=pd.MultiIndex.from_tuples(
                    [], names=["Asset_Class", "Asset_Category", "Security"]
                ),
            )

        # Convert nested dict to DataFrame
        df = pd.DataFrame.from_dict(
            {row_key: dict(col_dict) for row_key, col_dict in data.items()},
            orient="index",
        )

        # Set MultiIndex for rows
        df.index = pd.MultiIndex.from_tuples(
            df.index,
            names=["Account_Type", "Account_Category", "Account_Name", "Account_ID"],
        )

        # Set MultiIndex for columns
        df.columns = pd.MultiIndex.from_tuples(
            df.columns,
            names=["Asset_Class", "Asset_Category", "Security"],
        )

        # Fill NaN with 0 (accounts don't hold every security)
        df = df.fillna(0.0)

        # Sort for consistent ordering
        df = df.sort_index(axis=0).sort_index(axis=1)

        return df

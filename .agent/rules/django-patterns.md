---
trigger: always_on
---

# Django Patterns for cb3portfolio

## Engine Pattern (Pandas Calculations)

**All financial calculations use Engine classes with pandas.**

### Engine Structure

```python
import pandas as pd
from typing import Protocol
from .base import BaseEngine

class AllocationEngine(BaseEngine):
    """
    Centralized calculation logic using pandas.

    Key principles:
    - Use vectorized operations (no manual loops)
    - Return clean DataFrames (no formatting)
    - Use MultiIndex for hierarchical data
    """

    def calculate_drift(self, strategy) -> pd.DataFrame:
        """
        Calculate allocation drift using vectorized operations.

        Args:
            strategy: AllocationStrategy domain model

        Returns:
            DataFrame with columns: current_value, target_value, drift_value, drift_pct
            MultiIndex: (account_type, asset_class)
        """
        # Build DataFrame from queryset
        data = self._build_dataframe(strategy)

        # Vectorized calculations (NO manual loops!)
        data['drift_value'] = data['current_value'] - data['target_value']
        data['drift_pct'] = (
            data['drift_value'] / data['target_value']
        ).fillna(0)

        # Aggregate with MultiIndex
        result = data.groupby(['account_type', 'asset_class']).agg({
            'current_value': 'sum',
            'target_value': 'sum',
            'drift_value': 'sum',
            'drift_pct': 'mean'
        })

        return result

    def _build_dataframe(self, strategy) -> pd.DataFrame:
        """Convert Django queryset to pandas DataFrame."""
        # Use select_related/prefetch_related to avoid N+1 queries
        holdings = strategy.portfolio.holdings.select_related(
            'account', 'asset_class'
        ).values(
            'account__type',
            'asset_class__name',
            'current_value',
            'target_value'
        )

        return pd.DataFrame(list(holdings))
```

### Engine Rules

- ✅ **DO:** Use pandas vectorized operations
- ✅ **DO:** Return raw DataFrames (no formatting)
- ✅ **DO:** Use MultiIndex for hierarchical data
- ✅ **DO:** Document return structure in docstrings
- ❌ **DON'T:** Use manual loops over DataFrames
- ❌ **DON'T:** Format data in engines
- ❌ **DON'T:** Include business logic (that's in domain models)

## Formatter Pattern (Presentation)

**Formatters convert engine output to display-ready format.**

### Formatter Structure

```python
import pandas as pd
from decimal import Decimal

class AllocationFormatter:
    """
    Converts engine output to display format.

    Key principles:
    - Only presentation logic
    - No calculations
    - Template-ready output
    """

    def format_for_display(self, engine_result: pd.DataFrame) -> dict:
        """
        Format calculation results for template rendering.

        Args:
            engine_result: Raw DataFrame from engine

        Returns:
            Dict ready for template context
        """
        formatted = {
            'total_value': self._format_currency(
                engine_result['current_value'].sum()
            ),
            'allocations': self._format_allocations(engine_result),
            'needs_rebalance': self._check_rebalance_needed(engine_result),
        }
        return formatted

    def _format_currency(self, value: Decimal) -> str:
        """Format decimal as currency string."""
        return f"${value:,.2f}"

    def _format_percentage(self, value: float) -> str:
        """Format float as percentage string."""
        return f"{value:.2%}"

    def _format_allocations(self, df: pd.DataFrame) -> list[dict]:
        """Convert DataFrame rows to list of dicts for template."""
        allocations = []
        for idx, row in df.iterrows():
            allocations.append({
                'account_type': idx[0],
                'asset_class': idx[1],
                'current': self._format_currency(row['current_value']),
                'target': self._format_currency(row['target_value']),
                'drift': self._format_percentage(row['drift_pct']),
                'needs_attention': abs(row['drift_pct']) > 0.05,
            })
        return allocations

    def _check_rebalance_needed(self, df: pd.DataFrame) -> bool:
        """Check if any allocation exceeds drift threshold."""
        return (df['drift_pct'].abs() > 0.05).any()
```

### Formatter Rules

- ✅ **DO:** Only format data (no calculations)
- ✅ **DO:** Return template-ready structures
- ✅ **DO:** Handle currency/percentage formatting
- ❌ **DON'T:** Perform calculations
- ❌ **DON'T:** Access database
- ❌ **DON'T:** Contain business logic

## Domain Model Pattern

**Domain models contain business logic and constraints.**

### Domain Model Structure

```python
from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal

class AllocationStrategy(models.Model):
    """
    Domain model with business constraints.

    Key principles:
    - Enforce business rules in clean()
    - Domain methods delegate to engines
    - No calculation logic here
    """

    portfolio = models.ForeignKey('Portfolio', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Allocation strategies"

    def __str__(self):
        return f"{self.name} - {self.portfolio.name}"

    def clean(self):
        """Enforce business constraints."""
        allocations = self.allocations.all()
        total = sum(a.target_percentage for a in allocations)
        if total != Decimal('100.00'):
            raise ValidationError(
                f'Allocations must sum to 100%, currently {total}%'
            )

    def calculate_drift(self) -> pd.DataFrame:
        """
        Business logic method - delegates to engine.

        Domain models don't do calculations, they delegate.
        """
        from ..engines.allocation import AllocationEngine
        engine = AllocationEngine()
        return engine.calculate_drift(self)
```

### Domain Model Rules

- ✅ **DO:** Enforce business constraints in `clean()`
- ✅ **DO:** Delegate calculations to engines
- ✅ **DO:** Keep business logic here
- ✅ **DO:** Use Django's validation framework
- ❌ **DON'T:** Perform calculations directly
- ❌ **DON'T:** Format data for display
- ❌ **DON'T:** Handle HTTP concerns

## Service Pattern (Orchestration)

**Services orchestrate domain objects and external integrations.**

### Service Structure

```python
from django.db import transaction
from .models import Portfolio, Trade
from ..engines.rebalance import RebalanceEngine
import structlog

logger = structlog.get_logger(__name__)

class PortfolioService:
    """
    Services orchestrate domain objects and external integrations.

    Key principles:
    - Keep thin - domain logic stays in models
    - Handle transactions
    - Coordinate multiple operations
    """

    def __init__(self):
        self.rebalance_engine = RebalanceEngine()

    @transaction.atomic
    def execute_rebalance(self, portfolio_id: int) -> dict:
        """
        Calculate and execute portfolio rebalancing.

        Service orchestrates - domain logic stays in domain models.
        """
        # Get domain object with locking
        portfolio = Portfolio.objects.select_for_update().get(
            pk=portfolio_id
        )

        # Calculate using engine
        trades_df = self.rebalance_engine.calculate_trades(portfolio)

        # Create trade records (orchestration)
        trades = self._create_trade_records(portfolio, trades_df)

        # Log structured data
        logger.info(
            "rebalance_executed",
            portfolio_id=portfolio.id,
            trade_count=len(trades),
            total_value=float(portfolio.total_value),
        )

        return {
            'portfolio': portfolio,
            'trades': trades,
            'execution_date': timezone.now(),
        }

    def _create_trade_records(self, portfolio, trades_df):
        """Create Trade model instances from DataFrame."""
        trades = []
        for _, row in trades_df.iterrows():
            trade = Trade.objects.create(
                portfolio=portfolio,
                asset_class_id=row['asset_class_id'],
                account_id=row['account_id'],
                action=row['action'],
                quantity=row['quantity'],
                price=row['price'],
            )
            trades.append(trade)
        return trades
```

### Service Rules

- ✅ **DO:** Orchestrate domain objects
- ✅ **DO:** Handle transactions
- ✅ **DO:** Manage external integrations
- ✅ **DO:** Keep thin (delegate to domain)
- ❌ **DON'T:** Contain business logic
- ❌ **DON'T:** Perform calculations
- ❌ **DON'T:** Format data

## View Pattern (Thin Controllers)

**Views handle HTTP only - no business logic.**

### View Structure

```python
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Portfolio
from ..engines.allocation import AllocationEngine
from ..formatters.allocation import AllocationFormatter

@login_required
def portfolio_detail(request, pk):
    """
    Display portfolio with allocation analysis.

    View handles HTTP only - no business logic.
    """
    # Get domain object
    portfolio = get_object_or_404(Portfolio, pk=pk)

    # Use engine for calculations
    engine = AllocationEngine()
    calculation_result = engine.calculate_drift(portfolio.strategy)

    # Use formatter for presentation
    formatter = AllocationFormatter()
    display_data = formatter.format_for_display(calculation_result)

    # Render template
    return render(request, 'portfolio_detail.html', {
        'portfolio': portfolio,
        'data': display_data,
    })
```

### View Rules

- ✅ **DO:** Handle HTTP requests/responses
- ✅ **DO:** Orchestrate engines and formatters
- ✅ **DO:** Use `get_object_or_404` for safety
- ✅ **DO:** Keep thin (orchestration only)
- ❌ **DON'T:** Contain business logic
- ❌ **DON'T:** Perform calculations
- ❌ **DON'T:** Format data (use formatters)

## Database Query Optimization

### Always Use select_related/prefetch_related

```python
# ✅ DO: Optimize queries
portfolios = Portfolio.objects.select_related('strategy').prefetch_related(
    'accounts', 'accounts__holdings'
)

# ❌ DON'T: N+1 queries
portfolios = Portfolio.objects.all()
for portfolio in portfolios:
    strategy = portfolio.strategy  # Separate query!
    accounts = portfolio.accounts.all()  # N more queries!
```

### Query in Database, Not Python

```python
# ✅ DO: Filter in database
high_value = Portfolio.objects.filter(total_value__gt=100000)

# ❌ DON'T: Filter in Python
all_portfolios = Portfolio.objects.all()
high_value = [p for p in all_portfolios if p.total_value > 100000]
```

## Common Anti-Patterns to Avoid

### ❌ Business Logic in Views

```python
# BAD
def portfolio_view(request, pk):
    portfolio = Portfolio.objects.get(pk=pk)
    drift = 0
    for account in portfolio.accounts.all():
        drift += account.current_value - account.target_value
    return render(request, 'template.html', {'drift': drift})
```

### ✅ Use Domain Methods + Engines

```python
# GOOD
def portfolio_view(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk)
    drift_data = portfolio.calculate_drift()
    formatted_data = AllocationFormatter().format_for_display(drift_data)
    return render(request, 'template.html', {'data': formatted_data})
```

### ❌ Mixing Calculation and Formatting

```python
# BAD
def calculate_allocation(portfolio):
    allocation = calculate_raw_values()
    return f"Stocks: {allocation['stocks']:.2%}"  # Formatting!

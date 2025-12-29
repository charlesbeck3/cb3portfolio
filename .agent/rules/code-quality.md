---
trigger: always_on
---

# Code Quality & Performance Standards

## Pre-Commit Checklist

**All must pass before committing:**
```bash
uv run ruff format .      # Format
uv run ruff check .       # Lint
uv run mypy .            # Type check
uv run pytest            # Test
uv run pytest --cov --cov-fail-under=90  # Coverage
```

## Python Standards

### Type Hints (Required)
```python
# ✅ DO
from decimal import Decimal
def calculate_drift(current: Decimal, target: Decimal) -> Decimal:
    return current - target

# ❌ DON'T
def calculate_drift(current, target):
    return current - target
```

### Docstrings (Required for public functions - Google style)
```python
# ✅ DO
def calculate_portfolio_value(holdings: list[Holding], as_of_date: date) -> Decimal:
    """
    Calculate total portfolio value as of a specific date.

    Args:
        holdings: List of portfolio holdings
        as_of_date: Date for valuation

    Returns:
        Total portfolio value

    Raises:
        ValueError: If holdings list is empty
    """
    if not holdings:
        raise ValueError("Holdings list cannot be empty")
    return sum(h.current_value for h in holdings)
```

### Import Organization
```python
# Standard library
from datetime import date
from decimal import Decimal

# Third-party
import pandas as pd
from django.db import models

# First-party
from cb3portfolio.domain.models import Portfolio

# Local
from .engines import AllocationEngine
```

### Naming

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

## Performance Rules

### ALWAYS Vectorize Pandas (10-20x faster)
```python
# ✅ DO - Vectorized
df['drift'] = df['current_value'] - df['target_value']
df['drift_pct'] = df['drift'] / df['target_value']
df['needs_rebalance'] = df['drift_pct'].abs() > 0.05

# ❌ DON'T - Loops (SLOW!)
for idx, row in df.iterrows():
    df.at[idx, 'drift'] = row['current_value'] - row['target_value']
```

### ALWAYS Optimize Django Queries
```python
# ✅ DO - Avoid N+1 queries
portfolios = Portfolio.objects.select_related(
    'strategy'
).prefetch_related(
    'accounts__holdings__asset_class'
)

# ❌ DON'T - N+1 queries
portfolios = Portfolio.objects.all()  # Then access relations in loop
```

### Filter in Database, Not Python
```python
# ✅ DO
Portfolio.objects.filter(total_value__gt=100000)
stats = Portfolio.objects.aggregate(total=Sum('total_value'))

# ❌ DON'T
all_portfolios = Portfolio.objects.all()
high_value = [p for p in all_portfolios if p.total_value > 100000]
```

### Bulk Operations
```python
# ✅ DO
Holding.objects.bulk_create(holdings)
Portfolio.objects.filter(needs_sync=False).update(needs_sync=True)

# ❌ DON'T
for holding in holdings:
    holding.save()
```

## Money = Decimal (NEVER float)
```python
# ✅ DO
portfolio_value = Decimal('1234567.89')
allocation_pct = Decimal('60.00')
target = portfolio_value * (allocation_pct / Decimal('100'))

# ❌ DON'T
portfolio_value = 1234567.89  # Float = precision loss!
```

## Error Handling
```python
# ✅ DO - Specific exceptions
try:
    portfolio = Portfolio.objects.get(pk=portfolio_id)
except Portfolio.DoesNotExist:
    logger.warning("portfolio_not_found", portfolio_id=portfolio_id)
    raise Http404("Portfolio not found")

# ❌ DON'T
except:  # Bare except
except Exception:  # Too broad
```

## Logging (Use structlog)
```python
import structlog
logger = structlog.get_logger(__name__)

# ✅ DO
logger.info("portfolio_rebalanced",
    portfolio_id=portfolio.id,
    trade_count=len(trades))

# ❌ DON'T
print(f"Rebalanced {portfolio.id}")
logger.info(f"Rebalanced {portfolio.id}")  # No f-strings
```

## Avoid These Code Smells

- **Long functions**: Keep under 50 lines, extract smaller functions
- **Deep nesting**: Max 3 levels, use guard clauses
- **Magic numbers**: Use named constants
- **Code duplication**: Extract into functions
- **Unclear names**: `portfolio_total_value` not `ptv`

## Security
```python
# ✅ DO
logger.info("user_login", user_id=user.id)
validate_email(email)  # Django validators

# ❌ NEVER
logger.info("user_login", password=password)  # Log sensitive data
```

## Performance Checklist

- ✅ Pandas vectorization (not loops)?
- ✅ select_related/prefetch_related for Django queries?
- ✅ Filter/aggregate in database?
- ✅ Bulk operations for multiple records?
- ✅ Decimal for all money calculations?

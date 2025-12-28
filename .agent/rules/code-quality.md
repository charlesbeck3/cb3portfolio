---
trigger: always_on
---

# Code Quality & Performance Standards

## Code Quality Checks

### Before Every Commit

**ALL of these must pass:**

```bash
# 1. Format code
ruff format .

# 2. Check linting
ruff check .

# 3. Type checking
mypy .

# 4. Run tests
pytest

# 5. Verify coverage
pytest --cov --cov-fail-under=90
```

## Python Code Standards

### Type Hints

**Type hints are required on all functions.**

```python
# ✅ DO: Full type hints
from decimal import Decimal
import pandas as pd

def calculate_drift(
    current: Decimal,
    target: Decimal
) -> Decimal:
    """Calculate allocation drift."""
    return current - target

def process_data(
    portfolio: Portfolio,
    date_range: tuple[date, date] | None = None
) -> pd.DataFrame:
    """Process portfolio data."""
    pass

# ❌ DON'T: Missing type hints
def calculate_drift(current, target):
    return current - target
```

### Docstrings

**Docstrings required for all public functions (Google style).**

```python
# ✅ DO: Complete docstring
def calculate_portfolio_value(
    holdings: list[Holding],
    as_of_date: date
) -> Decimal:
    """
    Calculate total portfolio value as of a specific date.

    Args:
        holdings: List of portfolio holdings
        as_of_date: Date for valuation

    Returns:
        Total portfolio value as Decimal

    Raises:
        ValueError: If holdings list is empty

    Example:
        >>> holdings = get_holdings(portfolio)
        >>> value = calculate_portfolio_value(holdings, date.today())
        >>> print(f"${value:,.2f}")
        $1,234,567.89
    """
    if not holdings:
        raise ValueError("Holdings list cannot be empty")

    return sum(h.current_value for h in holdings)

# ❌ DON'T: Missing or inadequate docstring
def calculate_portfolio_value(holdings, as_of_date):
    """Calculate value."""
    return sum(h.current_value for h in holdings)
```

### Code Organization

```python
# ✅ DO: Proper import organization
# Standard library
import sys
from datetime import date
from decimal import Decimal

# Third-party
import pandas as pd
from django.db import models

# First-party
from cb3portfolio.domain.models import Portfolio

# Local
from .engines import AllocationEngine

# ❌ DON'T: Disorganized imports
from .engines import AllocationEngine
import pandas as pd
from django.db import models
from datetime import date
```

### Naming Conventions

```python
# Classes: PascalCase
class AllocationEngine:
    pass

# Functions/methods: snake_case
def calculate_drift():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_ALLOCATION_PCT = Decimal('100.00')
DEFAULT_REBALANCE_THRESHOLD = Decimal('5.00')

# Private methods: _leading_underscore
def _build_dataframe():
    pass
```

### Code Clarity

```python
# ✅ DO: Clear variable names
portfolio_total_value = holdings.aggregate(Sum('current_value'))
rebalance_threshold = Decimal('5.00')

# ❌ DON'T: Unclear abbreviations
ptv = holdings.aggregate(Sum('current_value'))
rbt = Decimal('5.00')

# ✅ DO: Extract complex conditions
needs_rebalancing = abs(drift_percentage) > rebalance_threshold
is_taxable_account = account.type in ['INDIVIDUAL', 'JOINT']

if needs_rebalancing and is_taxable_account:
    # ...

# ❌ DON'T: Nested complex conditions
if abs(drift_percentage) > Decimal('5.00') and account.type in ['INDIVIDUAL', 'JOINT']:
    # ...
```

## Performance Standards

### Pandas Vectorization

**ALWAYS use vectorized operations. NO manual loops over DataFrames.**

```python
# ✅ DO: Vectorized operations (10-20x faster)
df['drift'] = df['current_value'] - df['target_value']
df['drift_pct'] = df['drift'] / df['target_value']
df['needs_rebalance'] = df['drift_pct'].abs() > 0.05

# ❌ DON'T: Manual loops (SLOW!)
for idx, row in df.iterrows():
    drift = row['current_value'] - row['target_value']
    df.at[idx, 'drift'] = drift
    df.at[idx, 'drift_pct'] = drift / row['target_value']
    df.at[idx, 'needs_rebalance'] = abs(drift / row['target_value']) > 0.05

# ✅ DO: Batch operations
df['category'] = df['value'].apply(categorize_value)  # If necessary
# But prefer: df['category'] = pd.cut(df['value'], bins, labels)

# ❌ DON'T: Row-by-row operations
for idx, row in df.iterrows():
    df.at[idx, 'category'] = categorize_value(row['value'])
```

### Database Query Optimization

**ALWAYS use select_related and prefetch_related to avoid N+1 queries.**

```python
# ✅ DO: Optimized queries
portfolios = Portfolio.objects.select_related(
    'strategy'
).prefetch_related(
    'accounts',
    'accounts__holdings',
    'accounts__holdings__asset_class'
)

for portfolio in portfolios:
    # All data loaded in 2-3 queries
    strategy = portfolio.strategy
    for account in portfolio.accounts.all():
        for holding in account.holdings.all():
            print(holding.asset_class.name)

# ❌ DON'T: N+1 queries
portfolios = Portfolio.objects.all()

for portfolio in portfolios:
    strategy = portfolio.strategy  # Query for each portfolio
    for account in portfolio.accounts.all():  # Query for each portfolio
        for holding in account.holdings.all():  # Query for each account
            print(holding.asset_class.name)  # Query for each holding
```

### Query in Database, Not Python

```python
# ✅ DO: Filter in database
high_value_portfolios = Portfolio.objects.filter(
    total_value__gt=100000
).select_related('strategy')

# ✅ DO: Aggregate in database
from django.db.models import Sum, Avg
stats = Portfolio.objects.aggregate(
    total=Sum('total_value'),
    average=Avg('total_value')
)

# ❌ DON'T: Load everything then filter in Python
all_portfolios = Portfolio.objects.all()
high_value = [p for p in all_portfolios if p.total_value > 100000]

# ❌ DON'T: Calculate in Python
total = sum(p.total_value for p in Portfolio.objects.all())
```

### Use Django ORM Efficiently

```python
# ✅ DO: Bulk operations
holdings = [
    Holding(account=account, asset_class=stocks, current_value=1000)
    for account in accounts
]
Holding.objects.bulk_create(holdings)

# ✅ DO: Update in bulk
Portfolio.objects.filter(
    last_updated__lt=yesterday
).update(needs_sync=True)

# ❌ DON'T: Individual saves
for account in accounts:
    holding = Holding(account=account, asset_class=stocks, current_value=1000)
    holding.save()

# ❌ DON'T: Individual updates
for portfolio in Portfolio.objects.filter(last_updated__lt=yesterday):
    portfolio.needs_sync = True
    portfolio.save()
```

## Decimal Usage for Money

**ALWAYS use Decimal for money. NEVER use float.**

```python
from decimal import Decimal

# ✅ DO: Use Decimal
portfolio_value = Decimal('1234567.89')
allocation_pct = Decimal('60.00')

# Decimal arithmetic
target_value = portfolio_value * (allocation_pct / Decimal('100'))

# ✅ DO: Convert from database
current_value = Decimal(str(row['current_value']))

# ❌ DON'T: Use float for money
portfolio_value = 1234567.89  # WRONG!
allocation_pct = 60.00  # WRONG!

# ❌ DON'T: Float arithmetic with money
target_value = portfolio_value * (allocation_pct / 100)  # PRECISION LOSS!
```

## Error Handling

### Explicit Error Handling

```python
# ✅ DO: Specific exceptions
try:
    portfolio = Portfolio.objects.get(pk=portfolio_id)
except Portfolio.DoesNotExist:
    logger.warning("portfolio_not_found", portfolio_id=portfolio_id)
    raise Http404("Portfolio not found")
except Exception as e:
    logger.error("unexpected_error", error=str(e))
    raise

# ❌ DON'T: Bare except
try:
    portfolio = Portfolio.objects.get(pk=portfolio_id)
except:  # NEVER DO THIS
    pass

# ❌ DON'T: Catch too broadly
try:
    portfolio = Portfolio.objects.get(pk=portfolio_id)
except Exception:  # Too broad
    pass
```

### Validation

```python
# ✅ DO: Validate inputs
def calculate_drift(current: Decimal, target: Decimal) -> Decimal:
    """Calculate allocation drift."""
    if target == 0:
        raise ValueError("Target value cannot be zero")

    return current - target

# ✅ DO: Use Django's validation
class AllocationStrategy(models.Model):
    def clean(self):
        """Validate business rules."""
        total = sum(a.target_percentage for a in self.allocations.all())
        if total != Decimal('100.00'):
            raise ValidationError(
                f'Allocations must sum to 100%, currently {total}%'
            )
```

## Logging

**Use structlog for structured logging.**

```python
import structlog

logger = structlog.get_logger(__name__)

# ✅ DO: Structured logging
logger.info(
    "portfolio_rebalanced",
    portfolio_id=portfolio.id,
    trade_count=len(trades),
    total_value=float(portfolio.total_value),
    execution_time=elapsed_time
)

logger.error(
    "calculation_failed",
    portfolio_id=portfolio.id,
    error=str(e),
    exc_info=True
)

# ❌ DON'T: Print statements
print(f"Rebalanced portfolio {portfolio.id}")

# ❌ DON'T: String formatting in logs
logger.info(f"Portfolio {portfolio.id} rebalanced with {len(trades)} trades")
```

## Code Smells to Avoid

### Long Functions

```python
# ❌ DON'T: Functions over 50 lines
def process_portfolio(portfolio):
    # 100 lines of code
    pass

# ✅ DO: Break into smaller functions
def process_portfolio(portfolio):
    """Orchestrate portfolio processing."""
    drift = calculate_drift(portfolio)
    trades = generate_trades(drift)
    result = execute_trades(trades)
    return result
```

### Deep Nesting

```python
# ❌ DON'T: More than 3 levels of nesting
if portfolio:
    if portfolio.strategy:
        for account in portfolio.accounts.all():
            if account.is_active:
                for holding in account.holdings.all():
                    # Too deep!
                    pass

# ✅ DO: Extract functions, use guard clauses
def process_portfolio(portfolio):
    if not portfolio or not portfolio.strategy:
        return

    for account in get_active_accounts(portfolio):
        process_account_holdings(account)
```

### Magic Numbers

```python
# ❌ DON'T: Magic numbers
if drift_pct > 0.05:  # What is 0.05?
    rebalance()

# ✅ DO: Named constants
REBALANCE_THRESHOLD = Decimal('5.00')  # 5% drift threshold

if drift_pct > REBALANCE_THRESHOLD:
    rebalance()
```

### Code Duplication

```python
# ❌ DON'T: Duplicate code
result1 = data1['current'] - data1['target']
result2 = data2['current'] - data2['target']
result3 = data3['current'] - data3['target']

# ✅ DO: Extract function
def calculate_drift(data: pd.DataFrame) -> pd.Series:
    return data['current'] - data['target']

result1 = calculate_drift(data1)
result2 = calculate_drift(data2)
result3 = calculate_drift(data3)
```

## Performance Benchmarking

### Measure Before Optimizing

```python
import time

# Benchmark calculation time
start = time.time()
result = engine.calculate_drift(portfolio)
elapsed = time.time() - start

logger.info(
    "calculation_completed",
    portfolio_id=portfolio.id,
    execution_time=elapsed
)

# Expect 10x+ improvement with pandas vectorization
```

### Profile Slow Code

```bash
# Profile code
python -m cProfile -o profile.stats manage.py runscript test_performance

# Analyze results
python -m pstats profile.stats
```

## Security Considerations

### Never Log Sensitive Data

```python
# ✅ DO: Log safely
logger.info("user_login", user_id=user.id)

# ❌ DON'T: Log passwords, keys, tokens
logger.info("user_login", password=password)  # NEVER!
logger.info("api_call", api_key=api_key)  # NEVER!
```

### Input Validation

```python
# ✅ DO: Validate and sanitize
from django.core.validators import validate_email

def create_user(email: str) -> User:
    try:
        validate_email(email)
    except ValidationError:
        raise ValueError("Invalid email address")

    return User.objects.create(email=email)
```

## Quick Reference

### Before Committing

```bash
# 1. Format
ruff format .

# 2. Lint
ruff check .

# 3. Type check
mypy .

# 4. Test
pytest

# 5. Coverage
pytest --cov --cov-fail-under=90
```

### Performance Checklist

- ✅ Using pandas vectorization (not loops)?
- ✅ Using select_related/prefetch_related?

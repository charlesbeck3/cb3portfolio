---
trigger: always_on
---

# Testing Standards for cb3portfolio

## Testing Requirements

**Comprehensive test coverage is non-negotiable (~94% target).**

- Tests written alongside or after implementation
- All code paths must be covered
- Financial calculations require golden reference tests
- Test hierarchy: Unit → Integration → E2E

## Test Types

### 1. Unit Tests
**Test individual functions and methods in isolation.**

```python
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from cb3portfolio.models import AllocationStrategy, Allocation

@pytest.fixture
def portfolio_with_allocations(db):
    """Reusable test data fixture."""
    from cb3portfolio.models import Portfolio, AssetClass

    portfolio = Portfolio.objects.create(
        name="Test Portfolio",
        description="For testing"
    )

    stocks = AssetClass.objects.create(name="Stocks")
    bonds = AssetClass.objects.create(name="Bonds")

    strategy = AllocationStrategy.objects.create(
        portfolio=portfolio,
        name="60/40"
    )

    Allocation.objects.create(
        strategy=strategy,
        asset_class=stocks,
        target_percentage=Decimal('60.00')
    )
    Allocation.objects.create(
        strategy=strategy,
        asset_class=bonds,
        target_percentage=Decimal('40.00')
    )

    return strategy

def test_allocation_sum_constraint(portfolio_with_allocations):
    """Test business constraint enforcement."""
    strategy = portfolio_with_allocations

    # Add allocation that breaks constraint
    cash = AssetClass.objects.create(name="Cash")
    Allocation.objects.create(
        strategy=strategy,
        asset_class=cash,
        target_percentage=Decimal('10.00')
    )

    # Should raise validation error (sum = 110%)
    with pytest.raises(ValidationError) as exc_info:
        strategy.full_clean()

    assert "must sum to 100%" in str(exc_info.value)

def test_drift_calculation(portfolio_with_allocations):
    """Test engine calculation."""
    strategy = portfolio_with_allocations

    # Create holdings with drift
    # ... setup test data ...

    result = strategy.calculate_drift()

    assert result is not None
    assert 'drift_pct' in result.columns
    assert len(result) == 2  # Two asset classes
```

### 2. Integration Tests
**Test complete workflows across multiple components.**

```python
def test_portfolio_rebalancing_workflow(db):
    """Test complete rebalancing workflow."""
    from cb3portfolio.models import Portfolio
    from cb3portfolio.services import PortfolioService

    # Setup
    portfolio = create_test_portfolio_with_drift()
    service = PortfolioService()

    # Execute
    result = service.execute_rebalance(portfolio.id)

    # Verify
    assert result['portfolio'].id == portfolio.id
    assert len(result['trades']) > 0
    assert all(trade.portfolio_id == portfolio.id for trade in result['trades'])
```

### 3. Golden Reference Tests
**CRITICAL: Required for all financial calculations.**

Golden reference tests use real-world portfolio data to validate calculations against known good results. This is essential because financial calculation errors could result in material losses.

```python
import pytest
import pandas as pd
from decimal import Decimal
from cb3portfolio.engines.allocation import AllocationEngine

def test_allocation_calculation_real_world_data(db):
    """
    Golden reference test with real portfolio scenario.
    Critical for financial calculations.
    """
    # Load real portfolio data
    portfolio = create_real_portfolio_scenario()

    # Calculate using engine
    engine = AllocationEngine()
    result = engine.calculate_drift(portfolio.strategy)

    # Load golden reference (known good results)
    expected = pd.read_json('tests/fixtures/golden/allocation_drift.json')

    # Compare with tolerance for floating point
    pd.testing.assert_frame_equal(
        result,
        expected,
        rtol=0.01,  # 1% relative tolerance
        atol=0.01   # 1% absolute tolerance
    )

def create_real_portfolio_scenario():
    """
    Create real-world test scenario.
    This data comes from actual portfolio analysis.
    """
    from cb3portfolio.models import Portfolio, Account, Holding, AssetClass

    portfolio = Portfolio.objects.create(
        name="Retirement Portfolio",
        description="Real scenario from 2024-Q4"
    )

    # Create accounts with realistic balances
    traditional_401k = Account.objects.create(
        portfolio=portfolio,
        name="Fidelity 401k",
        type="401K",
        balance=Decimal('250000.00')
    )

    roth_ira = Account.objects.create(
        portfolio=portfolio,
        name="Vanguard Roth IRA",
        type="ROTH_IRA",
        balance=Decimal('75000.00')
    )

    # Create realistic holdings
    us_stocks = AssetClass.objects.create(name="US Stocks")
    Holding.objects.create(
        account=traditional_401k,
        asset_class=us_stocks,
        current_value=Decimal('150000.00'),
        target_value=Decimal('140000.00')
    )

    # ... more realistic setup ...

    return portfolio
```

### Golden Reference Test Rules

- ✅ **DO:** Use real-world portfolio data
- ✅ **DO:** Document data source and date
- ✅ **DO:** Set appropriate tolerance (0.01 typical)
- ✅ **DO:** Store expected results in fixtures
- ✅ **DO:** Test edge cases (empty portfolio, single asset, etc.)
- ❌ **DON'T:** Use contrived/fake data
- ❌ **DON'T:** Skip these tests (they're critical!)

### 4. E2E Tests (Playwright)
**Test complete user workflows in browser.**

```python
import pytest
from playwright.sync_api import Page, expect

@pytest.mark.e2e
def test_portfolio_rebalancing_workflow(page: Page, live_server):
    """Test complete user workflow."""
    # Login
    page.goto(f"{live_server.url}/login/")
    page.fill('input[name="username"]', 'testuser')
    page.fill('input[name="password"]', 'testpass123')
    page.click('button[type="submit"]')

    # Navigate to portfolio
    page.goto(f"{live_server.url}/portfolio/1/")

    # Verify drift calculations displayed
    expect(page.locator('.drift-indicator')).to_be_visible()
    drift_values = page.locator('.drift-value').all_text_contents()
    assert len(drift_values) > 0

    # Trigger rebalance
    page.click('button:has-text("Calculate Rebalance")')

    # Wait for calculation
    expect(page.locator('.rebalance-results')).to_be_visible()

    # Verify trade recommendations
    trades = page.locator('.trade-recommendation')
    expect(trades).to_have_count(2)

    # Confirm rebalance
    page.click('button:has-text("Execute Trades")')

    # Verify success message
    expect(page.locator('.success-message')).to_contain_text(
        'Rebalancing completed successfully'
    )
```

## Test Commands

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_engines.py

# Run specific test
pytest tests/test_engines.py::test_allocation_drift

# Run tests matching pattern
pytest -k test_allocation

# Run with print statements visible
pytest -s

# Run E2E tests with browser visible
pytest tests/e2e/ --headed

# Run E2E tests headless (for CI)
pytest tests/e2e/
```

### Coverage Requirements

```bash
# Generate coverage report
pytest --cov --cov-report=html

# View coverage report
open htmlcov/index.html

# Coverage must be >90%
pytest --cov --cov-fail-under=90
```

## Test Organization

### File Naming Convention

**Test files MUST mirror production code structure and naming.**

```
Production Structure              Test Structure
─────────────────────             ─────────────────────
cb3portfolio/
├── models/
│   ├── __init__.py              tests/
│   ├── portfolio.py             ├── models/
│   ├── account.py               │   ├── __init__.py
│   └── allocation.py            │   ├── test_portfolio.py
├── engines/                     │   ├── test_account.py
│   ├── __init__.py              │   └── test_allocation.py
│   ├── allocation.py            ├── engines/
│   └── rebalance.py             │   ├── __init__.py
├── formatters/                  │   ├── test_allocation.py
│   ├── __init__.py              │   └── test_rebalance.py
│   ├── currency.py              ├── formatters/
│   └── percentage.py            │   ├── __init__.py
├── services/                    │   ├── test_currency.py
│   ├── __init__.py              │   └── test_percentage.py
│   └── portfolio_service.py     └── services/
└── views/                           ├── __init__.py
    ├── __init__.py                  ├── test_portfolio_service.py
    ├── portfolio_views.py           └── views/
    └── dashboard_views.py               ├── __init__.py
                                         ├── test_portfolio_views.py
                                         └── test_dashboard_views.py
```

### Naming Rules

1. **Module tests:** `test_{module_name}.py`
   - `models/portfolio.py` → `tests/models/test_portfolio.py`
   - `engines/allocation.py` → `tests/engines/test_allocation.py`

2. **Directory structure:** Mirror production directories exactly
   - If production has `cb3portfolio/engines/`, tests have `tests/engines/`
   - Maintain same nesting levels

3. **Test function names:** `test_{function_or_method}_{scenario}`
   ```python
   # For portfolio.py::Portfolio.calculate_total_value()
   def test_calculate_total_value_with_multiple_accounts():
       pass

   def test_calculate_total_value_empty_portfolio():
       pass
   ```

### Benefits of Mirroring Structure

- **Easy navigation:** Find tests for any production file instantly
- **Clear ownership:** Each test file maps to exactly one production file
- **Refactoring safety:** Moving/renaming production code makes test updates obvious
- **IDE support:** Most IDEs can jump between test and production files

### Test File Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── fixtures/
│   └── golden/              # Golden reference data
│       ├── allocation_drift.json
│       └── rebalance_trades.json
├── models/                  # Mirrors cb3portfolio/models/
│   ├── __init__.py
│   ├── test_portfolio.py
│   ├── test_account.py
│   ├── test_holding.py
│   ├── test_asset_class.py
│   └── test_allocation.py
├── engines/                 # Mirrors cb3portfolio/engines/
│   ├── __init__.py
│   ├── test_allocation.py
│   └── test_rebalance.py
├── formatters/              # Mirrors cb3portfolio/formatters/
│   ├── __init__.py
│   ├── test_currency.py
│   └── test_percentage.py
├── services/                # Mirrors cb3portfolio/services/
│   ├── __init__.py
│   └── test_portfolio_service.py
├── views/                   # Mirrors cb3portfolio/views/
│   ├── __init__.py
│   ├── test_portfolio_views.py
│   └── test_dashboard_views.py
└── e2e/                     # End-to-end tests (special case)
    ├── conftest.py
    └── test_portfolio_workflow.py
```

### Fixture Organization (conftest.py)

```python
import pytest
from decimal import Decimal

@pytest.fixture
def sample_portfolio(db):
    """Basic portfolio for testing."""
    from cb3portfolio.models import Portfolio
    return Portfolio.objects.create(
        name="Test Portfolio",
        description="For testing"
    )

@pytest.fixture
def portfolio_with_accounts(sample_portfolio):
    """Portfolio with multiple account types."""
    from cb3portfolio.models import Account

    Account.objects.create(
        portfolio=sample_portfolio,
        name="401k",
        type="401K",
        balance=Decimal('100000.00')
    )
    Account.objects.create(
        portfolio=sample_portfolio,
        name="Roth IRA",
        type="ROTH_IRA",
        balance=Decimal('50000.00')
    )

    return sample_portfolio

@pytest.fixture
def portfolio_with_allocations(portfolio_with_accounts):
    """Complete portfolio setup for testing."""
    # ... full setup with allocations, holdings, etc.
    return portfolio_with_accounts
```

## Test

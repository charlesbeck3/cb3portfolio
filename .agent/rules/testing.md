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

### Test File Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── fixtures/
│   └── golden/              # Golden reference data
│       ├── allocation_drift.json
│       └── rebalance_trades.json
├── test_models.py           # Domain model tests
├── test_engines.py          # Calculation engine tests
├── test_formatters.py       # Formatter tests
├── test_services.py         # Service layer tests
├── test_views.py            # View tests
└── e2e/                     # End-to-end tests
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

## Testing Best Practices

### DO's

- ✅ Write descriptive test names that explain what's being tested
- ✅ Use fixtures for test data setup (DRY principle)
- ✅ Test one thing per test
- ✅ Use Arrange-Act-Assert pattern
- ✅ Test edge cases and error conditions
- ✅ Make tests independent (no order dependencies)
- ✅ Use `@pytest.mark` to categorize tests

### DON'Ts

- ❌ Don't test Django framework code (it's already tested)
- ❌ Don't create overly complex fixtures
- ❌ Don't use sleep() - use proper waits
- ❌ Don't skip golden reference tests for calculations
- ❌ Don't commit failing tests
- ❌ Don't test implementation details (test behavior)

## Test Markers

```python
import pytest

# Mark slow tests
@pytest.mark.slow
def test_complex_calculation():
    pass

# Mark tests requiring external services
@pytest.mark.integration
def test_external_api():
    pass

# Mark E2E tests
@pytest.mark.e2e
def test_browser_workflow():
    pass

# Skip tests conditionally
@pytest.mark.skipif(sys.platform == 'win32', reason="Unix only")
def test_unix_specific():
    pass
```

Run specific markers:
```bash
pytest -m "not slow"      # Skip slow tests
pytest -m integration     # Only integration tests
pytest -m e2e             # Only E2E tests
```

## Pre-Commit Testing

Before committing, ALWAYS run:

```bash
# 1. Format code
ruff format .

# 2. Check linting
ruff check .

# 3. Type check
mypy .

# 4. Run tests
pytest

# 5. Check coverage
pytest --cov --cov-fail-under=90
```

All must pass before committing.

## Continuous Integration

In CI/CD pipeline, run:

```bash
# Install dependencies
uv sync

# Run all quality checks
ruff format . --check
ruff check .
mypy .

# Run all tests with coverage
pytest --cov --cov-fail-under=90

# Run E2E tests
pytest tests/e2e/ --headed false
```

## Debugging Failed Tests

```bash
# Run with debugger on failure
pytest --pdb

# Run last failed tests
pytest --lf

# Run failed tests first, then others
pytest --ff

# Show local variables on failure
pytest -l

# Very verbose output
pytest -vv
```

## Golden Reference Test Creation

### Creating New Golden Reference

1. **Create real scenario:**
```python
def create_real_scenario():
    # Use actual portfolio data
    portfolio = create_portfolio_from_real_data()
    return portfolio
```

2. **Calculate expected results:**
```python
# Calculate using engine
result = engine.calculate(portfolio)

# Save as golden reference
result.to_json('tests/fixtures/golden/new_calculation.json')
```

3. **Verify independently:**
- Use spreadsheet to verify calculations
- Compare with manual calculations
- Document assumptions

4. **Create test:**
```python
def test_new_calculation_golden(db):
    portfolio = create_real_scenario()
    result = engine.calculate(portfolio)
    expe

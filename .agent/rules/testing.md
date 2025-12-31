---
trigger: always_on
---

---
trigger: always_on
---

# Testing Strategy for cb3portfolio

## Test Coverage Target: ~94%

Financial calculation errors = material dollar losses. Comprehensive testing is non-negotiable.

## Test Hierarchy

```
Unit Tests (fastest, most)
  ↓
Integration Tests (medium speed, medium coverage)
  ↓
E2E Tests (slowest, critical paths only)
  ↓
Golden Reference Tests (real scenarios, financial accuracy)
```

## Composition Testing Pattern

### Component-Level (Unit Tests)

**Calculator (No Django)**
```python
from portfolio.services.allocations.calculations import AllocationCalculator

def test_calculator_builds_presentation_df():
    """Test calculator in isolation."""
    calc = AllocationCalculator()

    holdings_df = pd.DataFrame({
        'account_id': [1],
        'asset_class_id': [1],
        'value': [50000.0],
    })

    result = calc.build_presentation_dataframe(
        holdings_df=holdings_df,
        asset_classes_df=pd.DataFrame(...),
        targets_map={},
        account_totals={1: Decimal('50000')},
    )

    assert not result.empty
    assert 'portfolio_actual' in result.columns
```

**DataProvider (With Django)**
```python
import pytest
from portfolio.services.allocations.data_providers import DjangoDataProvider

@pytest.mark.django_db
def test_data_provider_holdings(test_user, simple_holdings):
    """Test data provider queries."""
    provider = DjangoDataProvider()
    df = provider.get_holdings_df(test_user)

    assert not df.empty
    assert 'account_id' in df.columns
    assert 'value' in df.columns
```

**Formatter (No Django)**
```python
from portfolio.services.allocations.formatters import AllocationFormatter

def test_formatter_raw_values():
    """Test formatter returns raw numerics."""
    formatter = AllocationFormatter()

    df = pd.DataFrame({
        'asset_class_name': ['Equities'],
        'portfolio_actual': [50000.0],
        'portfolio_actual_pct': [62.5],
    })

    rows = formatter.to_presentation_rows(df, {}, {})

    assert isinstance(rows[0]['portfolio']['actual'], float)
    assert rows[0]['portfolio']['actual'] == 50000.0
```

### Engine-Level (Integration Tests)

```python
@pytest.mark.django_db
def test_engine_orchestration(test_user, simple_holdings):
    """Test full pipeline integration."""
    from portfolio.services.allocations import get_presentation_rows

    rows = get_presentation_rows(test_user)

    assert len(rows) > 0
    assert 'asset_class_name' in rows[0]
    assert 'portfolio' in rows[0]
    assert isinstance(rows[0]['portfolio']['actual'], float)
```

### Mock Dependencies

```python
from unittest.mock import Mock
from portfolio.services.allocations.engine import AllocationEngine

def test_engine_error_handling():
    """Test engine handles component failures."""
    mock_provider = Mock()
    mock_provider.get_holdings_df.side_effect = Exception("DB Error")

    engine = AllocationEngine(data_provider=mock_provider)
    rows = engine.get_presentation_rows(user=Mock())

    assert rows == []  # Returns empty on error
```

## Golden Reference Tests

**Use real portfolio scenarios to validate financial accuracy.**

```python
@pytest.mark.django_db
def test_golden_reference_allocation(test_portfolio):
    """
    Golden reference: Real portfolio allocation calculation.

    Scenario: Portfolio with $80,000
      - US Equities: $50,000 (62.5%)
      - Bonds: $30,000 (37.5%)

    Target: 60% US Equities, 40% Bonds

    Expected Variance:
      - US Equities: +2.5% ($2,000)
      - Bonds: -2.5% (-$2,000)
    """
    from portfolio.services.allocations import get_presentation_rows

    rows = get_presentation_rows(test_portfolio.user)

    equities_row = next(r for r in rows if r['asset_class_name'] == 'US Equities')
    bonds_row = next(r for r in rows if r['asset_class_name'] == 'Bonds')

    # Verify actual allocations
    assert abs(equities_row['portfolio']['actual'] - 50000.0) < 0.01
    assert abs(equities_row['portfolio']['actual_pct'] - 62.5) < 0.01

    # Verify variances
    assert abs(equities_row['portfolio']['variance_pct'] - 2.5) < 0.01
    assert abs(bonds_row['portfolio']['variance_pct'] - (-2.5)) < 0.01
```

## Fixtures Pattern

```python
# conftest.py
import pytest
from decimal import Decimal

@pytest.fixture
def test_user(db):
    """Create test user."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(username='test', email='test@example.com')

@pytest.fixture
def roth_account(test_portfolio):
    """Create Roth IRA account."""
    return Account.objects.create(
        portfolio=test_portfolio,
        name="Roth IRA",
        account_type=AccountType.ROTH_IRA,
    )

@pytest.fixture
def simple_holdings(roth_account, us_equities_asset_class):
    """Create basic holdings."""
    security = Security.objects.create(
        portfolio=roth_account.portfolio,
        symbol="VTI",
        asset_class=us_equities_asset_class,
    )

    return Holding.objects.create(
        account=roth_account,
        security=security,
        shares=Decimal('100'),
    )
```

## Test Organization

```
portfolio/tests/
├── conftest.py                    # Shared fixtures
├── test_models.py                 # Domain model tests
├── test_views.py                  # View tests
└── services/
    └── allocations/
        ├── test_calculations.py   # Calculator unit tests
        ├── test_data_providers.py # DataProvider tests
        ├── test_formatters.py     # Formatter unit tests
        ├── test_engine.py         # Engine integration tests
        └── test_golden_refs.py    # Golden reference scenarios
```

## Running Tests

```bash
# All tests
pytest

# Specific module
pytest portfolio/tests/services/allocations/test_calculations.py

# With coverage
pytest --cov=portfolio --cov-report=html

# Fast (skip slow E2E)
pytest -m "not e2e"

# Watch mode
ptw -- --testmon
```

## Test Markers

```python
@pytest.mark.unit           # Pure unit test
@pytest.mark.integration    # Integration test
@pytest.mark.django_db      # Requires database
@pytest.mark.services       # Service layer test
@pytest.mark.e2e            # End-to-end test (slow)
```

## Critical Testing Rules

1. **Calculator must have NO Django dependencies** - test without DB
2. **Test each component independently** before integration
3. **Golden reference tests for all financial calculations**
4. **Mock external dependencies** for unit tests
5. **Use factories/fixtures** for consistent test data
6. **Verify raw numeric values** not formatted strings
7. **Test error handling** not just happy path

## Anti-Patterns

❌ **Testing implementation details**
```python
# BAD - testing internal methods
def test_internal():
    engine._build_internal_df()  # Don't test private methods
```

❌ **Mixing concerns**
```python
# BAD - testing Calculator with Django
@pytest.mark.django_db
def test_calculator(test_user):
    calc = AllocationCalculator()
    result = calc.calculate(test_user)  # Calculator shouldn't take User!
```

❌ **Testing formatting in Python**
```python
# BAD - verifying formatted strings
assert rows[0]['value'] == "$50,000"  # Should verify float: 50000.0
```

✅ **Testing behavior**
```python
# GOOD - testing public API
def test_public_api():
    rows = get_presentation_rows(user)
    assert len(rows) > 0
```

✅ **Isolated components**
```python
# GOOD - Calculator with pure data
def test_calculator():
    calc = AllocationCalculator()
    result = calc.calculate(df)  # Pure pandas input
    assert result['portfolio_actual'].sum() > 0
```

✅ **Raw numeric values**
```python
# GOOD - verifying raw floats
assert isinstance(rows[0]['portfolio']['actual'], float)
assert abs(rows[0]['portfolio']['actual'] - 50000.0) < 0.01
```

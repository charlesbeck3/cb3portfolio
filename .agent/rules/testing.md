---
trigger: always_on
---

---
trigger: always_on
---

# Testing Standards for cb3portfolio

## 🚨 CRITICAL: Add to Existing Test Files First

**ALWAYS add new tests to existing test files. Only create new test files for entirely new modules.**

### Decision Tree

1. ✅ Find production file: `portfolio/services/pricing.py`
2. ✅ Find matching test: `portfolio/tests/services/test_pricing.py`
3. ✅ **If test file exists → ADD TESTS THERE**
4. ❌ Only create NEW file if testing brand new module

### Examples

**✅ CORRECT: Add to Existing File**
```python
# File: portfolio/tests/services/test_pricing.py (EXISTS!)
# Add new test class:

@pytest.mark.services
class TestPriceCaching:  # New functionality
    """Test price caching and staleness detection."""

    def test_is_stale_fresh_price(self, ...):
        pass
```

**❌ WRONG: Creating Unnecessary Files**
```python
# DON'T create:
portfolio/tests/services/test_pricing_cache.py      # Add to test_pricing.py
portfolio/tests/services/test_price_staleness.py    # Add to test_pricing.py
portfolio/tests/views/test_sidebar_performance.py   # Add to test_mixins.py
```

### When to Create New Test Files

**Only create new test file when:**
1. Testing brand new production module (never tested before)
2. New production directory requires matching test directory
3. Specialized category (benchmarks/, golden_reference/)

## Test Requirements

- Coverage target: **~94%**
- Test hierarchy: **Unit → Integration → E2E**
- Golden reference tests for financial calculations
- Tests written alongside implementation

## Test Types

### 1. Unit Tests
```python
@pytest.mark.unit
@pytest.mark.models
def test_allocation_sum_constraint(portfolio_with_allocations):
    """Test business constraint enforcement."""
    strategy = portfolio_with_allocations

    # Add invalid allocation
    cash = AssetClass.objects.create(name="Cash")
    TargetAllocation.objects.create(
        strategy=strategy,
        asset_class=cash,
        target_percent=Decimal('10.00')  # Sum = 110%
    )

    with pytest.raises(ValidationError) as exc:
        strategy.full_clean()

    assert "must sum to 100%" in str(exc.value)
```

### 2. Integration Tests
```python
@pytest.mark.integration
@pytest.mark.services
def test_price_update_workflow(db, test_user):
    """Test complete workflow across components."""
    service = PricingService()
    result = service.update_holdings_prices(test_user)

    assert result['updated_count'] > 0
```

### 3. Golden Reference Tests
```python
@pytest.mark.golden
@pytest.mark.calculations
def test_allocation_golden_reference():
    """Verify against known-correct real-world scenario."""
    scenario = load_golden_reference("allocation_drift.json")
    engine = AllocationCalculationEngine()
    result = engine.calculate_allocations(scenario['holdings_df'])

    for asset_class, expected in scenario['expected'].items():
        actual = result['by_asset_class'].loc[asset_class, 'current_value']
        assert abs(actual - expected) < 0.01
```

### 4. E2E Tests (Playwright)
```python
@pytest.mark.e2e
def test_rebalancing_workflow(page: Page, live_server, login_user):
    """Test complete user workflow in browser."""
    # Use login fixture to authenticate
    login_user('testuser')

    page.goto(f"{live_server.url}/portfolio/1/")
    expect(page.locator('.drift-indicator')).to_be_visible()
```

## File Organization

### Production-to-Test Mapping (1:1)

```
Production                    Test
─────────────────            ─────────────────
portfolio/
├── services/
│   ├── pricing.py          portfolio/tests/services/
│   └── allocation.py       ├── test_pricing.py
├── models/                 │   └── test_allocation.py
│   └── securities.py       └── models/
└── utils/                      ├── test_securities.py
    └── security.py             └── utils/
                                    └── test_security.py
```

### Test Class Organization

**Group related tests in same file using classes:**

```python
# portfolio/tests/services/test_pricing.py

@pytest.mark.services
class TestPricingService:
    """Core pricing service tests."""
    def test_update_prices(self): pass

@pytest.mark.services
class TestPriceCaching:
    """Price caching tests."""
    def test_is_stale(self): pass
    def test_update_if_stale(self): pass

@pytest.mark.services
class TestPriceHistory:
    """Historical price tests."""
    def test_get_price_at_datetime(self): pass
```

## Naming Conventions

### Files
- Production: `portfolio/services/pricing.py`
- Test: `portfolio/tests/services/test_pricing.py`

### Classes
- `TestPricingService` - Main functionality
- `TestPriceCaching` - Specific feature
- `TestSecurityValidation` - Another feature

### Functions
- `test_{function}_{scenario}`
- `test_calculate_drift_with_empty_portfolio()`
- `test_validate_user_owns_account_wrong_user()`

## Fixtures

### Shared Fixtures (conftest.py)
```python
@pytest.fixture
def test_user(db):
    """Standard test user."""
    from users.models import CustomUser
    return CustomUser.objects.create_user(
        username="testuser",
        email="test@example.com"
    )

@pytest.fixture
def base_system_data(db):
    """Base system data (account types, asset classes)."""
    from portfolio.services.seeder import SystemSeederService
    SystemSeederService().run()
    return get_system_data_namespace()
```

### File-Specific Fixtures
```python
# In portfolio/tests/services/test_pricing.py

@pytest.fixture
def pricing_service():
    """Pricing service instance."""
    return PricingService()

@pytest.fixture
def stale_prices(test_user, base_system_data):
    """Portfolio with old prices."""
    # Setup
    return portfolio
```

## pytest Markers

```python
@pytest.mark.unit           # No database
@pytest.mark.integration    # Database required
@pytest.mark.e2e           # Browser required
@pytest.mark.slow          # >1 second
@pytest.mark.services      # Service layer
@pytest.mark.models        # Model tests
@pytest.mark.views         # View tests
@pytest.mark.golden        # Golden reference
@pytest.mark.calculations  # Calculation engine
```

## Test Commands

```bash
# Run all tests
pytest

# Run specific file
pytest portfolio/tests/services/test_pricing.py

# Run specific class
pytest portfolio/tests/services/test_pricing.py::TestPriceCaching

# Run specific test
pytest portfolio/tests/services/test_pricing.py::TestPriceCaching::test_is_stale

# Run with markers
pytest -m services
pytest -m "services and integration"

# With coverage (must be >94%)
pytest --cov=portfolio --cov-report=html
pytest --cov --cov-fail-under=94

# Verbose
pytest -v

# Stop at first failure
pytest -x
```

## Key Principles

1. **✅ Add to existing files** - Don't proliferate test files
2. **✅ Use test classes** - Group related tests
3. **✅ Mirror structure** - 1:1 production-to-test mapping
4. **✅ Use fixtures** - DRY principle for setup
5. **✅ Mark appropriately** - Enable filtering
6. **✅ Name descriptively** - Clear test purpose
7. **❌ Don't create new files** - Unless testing new module

## Quick Reference

**Adding tests for existing code:**
1. Production: `portfolio/services/pricing.py`
2. Test file: `portfolio/tests/services/test_pricing.py`
3. Add class: `class TestPriceCaching:`
4. Add methods: `def test_is_stale_fresh_price(...):`
5. Mark: `@pytest.mark.services`

**Testing new code:**
1. New file: `portfolio/utils/reporting.py`
2. Create: `portfolio/tests/utils/test_reporting.py`
3. Follow structure above

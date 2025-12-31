---
trigger: always_on
---

---
trigger: always_on
---

# Architecture Principles for cb3portfolio

## Project Context

This is cb3portfolio, a Django-based personal portfolio management platform focused on tax-optimized investment management with asset location optimization and automated rebalancing capabilities. This is a **single-user personal tool**, not a multi-tenant SaaS application.

## Core Architectural Principles

### 1. Django-Native First

**ALWAYS prefer Django's built-in solutions over external dependencies.**

- Use Django's native features (e.g., native CSP support in Django 6.0)
- Only add external dependencies when Django doesn't provide the capability
- Avoid heavy frameworks or abstractions when Django can handle it
- Check Django documentation first before adding packages

### 2. Domain-Driven Design

**Business logic belongs in domain models, not views or templates.**

- Domain models enforce business constraints (e.g., allocation percentages sum to 100%)
- Services handle orchestration and external integrations
- Clear separation of concerns:
  - **Domain Models** - Business entities and rules
  - **Services** - Orchestration and coordination
  - **Views** - HTTP handling only
  - **Templates** - Presentation only

**Layer Flow:**
```
Domain Models → Services → Views → Templates
```

### 3. Calculation Architecture (Composition Pattern)

**All financial calculations use pandas DataFrames with clean component separation.**

The allocation module follows a **composition pattern with dependency injection**:

```
Engine (orchestration)
  ├── Calculator (pandas calculations)
  ├── DataProvider (Django ORM → pandas)
  └── Formatter (DataFrame → dict transformation)
```

**Component Responsibilities:**

1. **Calculator** - Pure calculation logic using pandas
   - Builds DataFrames from input data
   - Performs vectorized calculations (aggregations, variances, percentages)
   - Returns DataFrames with numeric results
   - No Django dependencies, fully unit testable

2. **DataProvider** - Data access layer
   - Fetches data from Django ORM
   - Converts to pandas DataFrames
   - Handles all database queries
   - Single source of data fetching

3. **Formatter** - Structure transformation
   - Converts DataFrames to template-ready dicts
   - Returns raw numeric values (no string formatting)
   - Organizes data for template consumption

4. **Engine** - Orchestration
   - Composes Calculator, DataProvider, Formatter
   - Exposes clean public API: `get_presentation_rows(user)`
   - Handles logging and error handling
   - Single entry point for views

**Why Composition Over Consolidation?**

- Better testability (mock each component independently)
- Single Responsibility Principle (each class has one clear job)
- Dependency injection enables testing without Django
- More maintainable as complexity grows
- Follows standard software engineering best practices
- Still provides clean API (views make single method call)

**Calculation Flow:**
```
View → Engine.get_presentation_rows(user)
         ├── DataProvider.get_holdings_df()
         ├── DataProvider.get_asset_classes_df()
         ├── Calculator.build_presentation_dataframe()
         └── Formatter.to_presentation_rows()
              → list[dict] with raw numerics
```

**View Pattern (Simplified):**
```python
from portfolio.services.allocations import get_presentation_rows

@login_required
def portfolio_dashboard(request):
    # Single clean API call
    rows = get_presentation_rows(user=request.user)
    return render(request, 'portfolio/dashboard.html', {
        'allocation_rows': rows,
    })
```

**Why Use Python's `Decimal` for Money?**
- Avoids floating-point precision errors in financial calculations
- Ensures exact decimal arithmetic
- Industry best practice for monetary values
- Use `Decimal` for all money calculations, convert to `float` only at template boundary

**Template Display:**
- Templates receive raw numeric values (float/int) in dicts
- All string formatting done via template filters: `|money`, `|percent`, `|number`
- No formatting strings in Python code

### 4. Simplicity Over Complexity

- Prefer simple, maintainable solutions
- Avoid premature optimization
- Choose well-maintained dependencies over complex custom solutions
- Consolidate documentation in README.md (single source of truth)
- Don't create separate architecture documents - keep it in README
- **Separate concerns, but compose cleanly**

### 5. Comprehensive Testing

- Comprehensive test coverage is non-negotiable (~94% target)
- **Golden reference tests with real-world data scenarios for financial calculations**
- Test hierarchy: Unit → Integration → E2E
- Tests written alongside or after implementation
- Financial calculation errors could result in material losses - tests provide confidence
- Composition pattern enables testing each component in isolation

## File Organization

```
cb3portfolio/
├── domain/          # Domain models and business logic
│   ├── models.py    # Django models with business methods
│   └── services.py  # Domain services
├── services/        # Calculation engines (pandas-based)
│   └── allocations/
│       ├── __init__.py         # Public API (convenience functions)
│       ├── engine.py           # AllocationEngine (orchestration)
│       ├── calculations.py     # AllocationCalculator (pure pandas)
│       ├── data_providers.py   # DjangoDataProvider (ORM → pandas)
│       ├── formatters.py       # AllocationFormatter (DataFrame → dict)
│       └── types.py            # TypedDict schemas
├── views.py         # Django views (thin, orchestration only)
├── urls.py
└── templates/       # Django templates
```

## Technology Stack

- **Python:** 3.14+
- **Framework:** Django 6.0
- **Calculations:** pandas (with MultiIndex)
- **Database:** SQLite (dev/test), PostgreSQL (production consideration)
- **Package Management:** uv
- **Linting/Formatting:** ruff
- **Type Checking:** mypy
- **Testing:** pytest with factories
- **E2E Testing:** Playwright

## Key Design Decisions

### Why Django-Native First?
- Reduces dependencies
- Leverages framework capabilities
- Better long-term maintenance
- Built-in security features

### Why Domain-Driven Design?
- Clear separation of concerns
- Business logic in appropriate places
- Easier to test
- Better code organization

### Why Pandas for Calculations?
- 10-20x performance improvement via vectorization
- Natural fit for financial data
- MultiIndex for hierarchical aggregations
- Industry standard for data analysis

### Why Composition Pattern?
- Better testability (unit test each component)
- Single Responsibility Principle
- Dependency injection for testing
- Maintainable as complexity grows
- Still provides clean API for views
- Aligns with software engineering best practices

### Why Single-User Focus?
- Simpler architecture
- No multi-tenancy complexity
- Faster development
- Personal tool optimization

## Code Patterns

### ✅ Good Pattern: Composition with Clean API

```python
# Module-level convenience function
from portfolio.services.allocations import get_presentation_rows

# View makes single call
rows = get_presentation_rows(user=request.user)

# Under the hood (engine.py):
class AllocationEngine:
    def __init__(self, calculator=None, data_provider=None, formatter=None):
        self.calculator = calculator or AllocationCalculator()
        self.data_provider = data_provider or DjangoDataProvider()
        self.formatter = formatter or AllocationFormatter()

    def get_presentation_rows(self, user):
        # 1. Get data
        holdings_df = self.data_provider.get_holdings_df(user)
        asset_classes_df = self.data_provider.get_asset_classes_df(user)

        # 2. Calculate
        presentation_df = self.calculator.build_presentation_dataframe(
            holdings_df, asset_classes_df, ...
        )

        # 3. Format for templates
        return self.formatter.to_presentation_rows(presentation_df, ...)
```

### ❌ Bad Pattern: View-Level Orchestration

```python
# DON'T DO THIS - too many steps in view
from portfolio.services.allocations.calculator import AllocationCalculator
from portfolio.services.allocations.data_provider import DjangoDataProvider
from portfolio.services.allocations.formatter import AllocationFormatter

def view(request):
    provider = DjangoDataProvider()
    calculator = AllocationCalculator()
    formatter = AllocationFormatter()

    holdings_df = provider.get_holdings_df(request.user)
    presentation_df = calculator.build_presentation_dataframe(holdings_df, ...)
    rows = formatter.to_presentation_rows(presentation_df, ...)
    # Too much orchestration in view!
```

### ❌ Bad Pattern: String Formatting in Python

```python
# DON'T DO THIS
return {'value': f"${row['value']:,.0f}"}  # NO!
df['value_fmt'] = df['value'].apply(lambda x: f"${x:,.0f}")  # NO!
```

### ✅ Good Pattern: Raw Values + Template Filters

```python
# Python: Return raw numeric values
return {'value': float(amount)}

# Template: Format with filters
<td>{{ row.value|money }}</td>
```

## Testing Strategy

### Component-Level Testing
```python
# Test Calculator in isolation (no Django)
def test_calculator():
    calculator = AllocationCalculator()
    df = pd.DataFrame({...})
    result = calculator.build_presentation_dataframe(df, ...)
    assert result['portfolio_actual'].sum() > 0

# Test DataProvider with Django
@pytest.mark.django_db
def test_data_provider(test_user):
    provider = DjangoDataProvider()
    df = provider.get_holdings_df(test_user)
    assert not df.empty

# Test Formatter in isolation
def test_formatter():
    formatter = AllocationFormatter()
    df = pd.DataFrame({...})
    rows = formatter.to_presentation_rows(df, ...)
    assert isinstance(rows[0]['portfolio']['actual'], float)
```

### Integration Testing
```python
@pytest.mark.django_db
def test_engine_integration(test_user):
    engine = AllocationEngine()
    rows = engine.get_presentation_rows(test_user)
    assert len(rows) > 0
```

### Golden Reference Testing
```python
@pytest.mark.django_db
def test_golden_reference(test_portfolio):
    """Test with real portfolio scenario."""
    engine = AllocationEngine()
    rows = engine.get_presentation_rows(test_portfolio.user)

    # Compare with known-good reference data
    assert abs(rows[0]['portfolio']['actual'] - 50000.0) < 0.01
```

## Migration Notes

When refactoring existing code:

1. **Identify Components**
   - What's pure calculation? → Calculator
   - What fetches from Django? → DataProvider
   - What transforms structure? → Formatter

2. **Extract Components**
   - Create separate classes with single responsibilities
   - Remove Django dependencies from Calculator
   - Move all ORM queries to DataProvider

3. **Build Engine**
   - Create Engine class that composes components
   - Expose clean public API methods
   - Handle logging and error handling

4. **Update Views**
   - Replace multi-step orchestration with single Engine call
   - Use module-level convenience functions

5. **Write Tests**
   - Unit test each component independently
   - Integration test Engine
   - Golden reference tests for calculations

## Anti-Patterns Summary

❌ **NEVER:**
- Format strings in Python (use template filters)
- Orchestrate multiple service classes in views
- Mix Django ORM with calculation logic
- Skip comprehensive testing for financial calculations
- Use `float` for monetary calculations (use `Decimal`)

✅ **ALWAYS:**
- Return raw numeric values from services
- Provide clean single-method API from Engine
- Separate calculations from data access
- Test each component independently
- Use pandas for vectorized calculations
- Validate financial calculations with golden reference tests

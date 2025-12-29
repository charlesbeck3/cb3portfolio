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

### 3. Calculation Architecture (UPDATED)

**All financial calculations use pandas DataFrames with consolidated Engine pattern.**

- Centralize ALL calculations and formatting in Engine classes (e.g., `AllocationCalculationEngine`)
- **Engine handles both calculation AND structure transformation**
- **NO separate Formatter classes** - formatting methods are private methods within Engine
- Use Python's `Decimal` type for monetary precision
- Never use `float` for money calculations

**Simplified Calculation Flow:**
```
Engine (calculations + structure transformation) → View → Template
```

**Engine Responsibilities:**
- Calculate all numeric values (including variances, percentages, aggregations)
- Transform DataFrames to template-ready dicts with raw numeric values
- Expose clean public API methods:
  - `get_presentation_rows(user)` - Dashboard/targets data
  - `get_holdings_rows(user, account_id)` - Holdings data
  - `calculate_allocations(df)` - Low-level calculations
- Keep internal methods private (prefixed with `_`)

**View Pattern (Simplified):**
```python
# Single clean API call
engine = AllocationCalculationEngine()
rows = engine.get_presentation_rows(user=user)
context["allocation_rows"] = rows
```

**Why consolidate Engine and Formatter?**
- Formatter was always used immediately after Engine (tight coupling)
- Formatter needed Engine's internal metadata (accounts, strategies)
- Eliminates boilerplate in views (no multi-step orchestration)
- Simpler testing (one service class instead of two)
- Clear single responsibility: "Calculate portfolio data and prepare it for display"
- Follows the principle: if two classes are always used together, they should be one class

**Template Display:**
- Templates receive raw numeric values in dicts
- All string formatting done via template filters: `|money`, `|percent`, `|number`
- No formatting strings in Python code

### 4. Simplicity Over Complexity

- Prefer simple, maintainable solutions
- Avoid premature optimization
- Choose well-maintained dependencies over complex custom solutions
- Consolidate documentation in README.md (single source of truth)
- Don't create separate architecture documents - keep it in README
- **If two classes are always used together, merge them**

### 5. Comprehensive Testing

- Comprehensive test coverage is non-negotiable (~94% target)
- **Golden reference tests with real-world data scenarios for financial calculations**
- Test hierarchy: Unit → Integration → E2E
- Tests written alongside or after implementation
- Financial calculation errors could result in material losses - tests provide confidence

## File Organization

```
cb3portfolio/
├── domain/          # Domain models and business logic
│   ├── models.py    # Django models with business methods
│   └── services.py  # Domain services
├── services/        # Calculation engines (pandas-based)
│   ├── allocation_calculations.py  # Engine with calculation + formatting
│   └── rebalancing.py
├── views.py         # Django views (thin, orchestration only)
├── urls.py
└── templates/       # Django templates
```

**Note:** No separate `formatters/` directory - formatting is private methods within Engine classes.

## Technology Stack

- **Python:** 3.12+
- **Framework:** Django 6.0
- **Calculations:** pandas (with MultiIndex)
- **Database:** SQLite (dev/test), PostgreSQL (production consideration)
- **Package Management:** uv
- **Linting/Formatting:** ruff
- **Type Checking:** mypy
- **Testing:** pytest
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

### Why Consolidate Engine and Formatter?
- Eliminates unnecessary abstraction
- Simplifies API surface
- Reduces boilerplate in views
- Easier to test and maintain
- Follows "always used together = should be together" principle

### Why Single-User Focus?
- Simpler architecture
- No multi-tenancy complexity
- Faster development
- Personal tool optimization

## Anti-Patterns to Avoid

### ❌ Separate Formatter Classes
```python
# OLD PATTERN (Don't do this)
engine = AllocationCalculationEngine()
formatter = AllocationPresentationFormatter()

df = engine.build_presentation_dataframe(user=user)
aggregated = engine.aggregate_presentation_levels(df)
_, accounts_by_type = engine._get_account_metadata(user)
strategies = engine._get_target_strategies(user)

rows = formatter.format_presentation_rows(
    aggregated_data=aggregated,
    accounts_by_type=accounts_by_type,
    target_strategies=strategies,
)
```

### ✅ Consolidated Engine
```python
# NEW PATTERN (Do this)
engine = AllocationCalculationEngine()
rows = engine.get_presentation_rows(user=user)
```

### ❌ Formatting in Python
```python
# Don't do this
return {'value': f"${amount:,.2f}"}  # NO!
```

### ✅ Raw Values for Templates
```python
# Do this
return {'value': float(amount)}  # YES - template handles formatting
```

## Migration Notes

When refactoring existing code:
1. Move all calculations to Engine methods
2. Move all DataFrame→dict transformation to private Engine methods
3. Create clean public API methods (`get_*_rows()`)
4. Delete separate Formatter classes
5. Update views to use single Engine method call
6. Ensure all tests pass and coverage maintained

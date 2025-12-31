# cb3portfolio

Django 6.0 personal portfolio management platform for tax-optimized investment tracking with automated rebalancing. Single-user application (not multi-tenant SaaS).

**Tech Stack:** Python 3.14, Django 6.0, pandas, pytest, uv, ruff, mypy

## Common Commands

```bash
# Development
uv run python manage.py runserver        # Start dev server
uv run python manage.py test             # Run Django tests
pytest                                   # Run all tests
pytest --cov=portfolio --cov-report=html # Test with coverage

# Code Quality
ruff check .                             # Lint
ruff format .                            # Format
mypy .                                   # Type check
pre-commit run --all-files              # Run all pre-commit hooks

# Database
uv run python manage.py makemigrations   # Create migrations
uv run python manage.py migrate          # Apply migrations
uv run python manage.py shell_plus       # Enhanced shell

# Testing
pytest portfolio/tests/services/allocations/  # Test specific module
pytest -v --tb=short                          # Verbose with short traceback
pytest -k "test_calculator"                   # Run tests matching pattern
```

## Project Structure

```
cb3portfolio/
├── portfolio/
│   ├── domain/              # Domain models & business logic
│   ├── services/            # Calculation engines
│   │   └── allocations/     # Allocation calculations (composition pattern)
│   ├── views.py             # Thin views (orchestration only)
│   ├── templates/           # Django templates
│   └── tests/               # Comprehensive test suite (~94% coverage)
├── .agent/
│   └── rules/               # Detailed architectural patterns
├── CLAUDE.md                # This file (quick reference)
└── README.md                # Full documentation
```

## Architecture: Composition Pattern

Services use **composition with dependency injection**:

```
Engine (orchestration)
  ├── Calculator (pure pandas calculations)
  ├── DataProvider (Django ORM → pandas)
  └── Formatter (DataFrame → dict)
```

**Data Flow:**
```
View → get_presentation_rows(user)
         → Engine orchestrates:
           DataProvider → Calculator → Formatter
             → list[dict] with raw floats
               → Template applies |money, |percent filters
```

## Key Rules

### ✅ Always Do:
- Views call module-level functions (e.g., `get_presentation_rows(user)`)
- Return raw numeric values to templates
- Templates format via custom filters (`|money`, `|percent`)
- Calculator uses pure pandas (no Django dependencies)
- DataProvider handles all ORM queries
- Use `Decimal` for money calculations, convert to `float` at template boundary
- Comprehensive testing (~94% target)
- Type hints with mypy

### ❌ Never Do:
- String formatting in Python
- Multi-step orchestration in views
- Django imports in Calculator
- Use `float` for money calculations (use `Decimal`)
- Skip tests for financial calculations

## Code Patterns

### View Pattern
```python
from portfolio.services.allocations import get_presentation_rows

@login_required
def dashboard(request):
    rows = get_presentation_rows(user=request.user)
    return render(request, 'portfolio/dashboard.html', {'rows': rows})
```

### Service Pattern
```python
# Module-level convenience function
def get_presentation_rows(user) -> list[dict]:
    from .engine import AllocationEngine
    return AllocationEngine().get_presentation_rows(user)

# Engine orchestrates components
class AllocationEngine:
    def __init__(self, calculator=None, data_provider=None, formatter=None):
        self.calculator = calculator or AllocationCalculator()
        self.data_provider = data_provider or DjangoDataProvider()
        self.formatter = formatter or AllocationFormatter()
```

### Testing Pattern
```python
# Unit test (no Django)
def test_calculator():
    calc = AllocationCalculator()
    result = calc.build_presentation_dataframe(df, ...)
    assert 'portfolio_actual' in result.columns

# Integration test (with Django)
@pytest.mark.django_db
def test_integration(test_user):
    rows = get_presentation_rows(test_user)
    assert len(rows) > 0

# Mock dependencies
def test_engine():
    engine = AllocationEngine(
        calculator=Mock(),
        data_provider=Mock(),
        formatter=Mock(),
    )
    # Test orchestration
```

## Development Workflow

1. **Write Tests First:** Golden reference tests for financial calculations
2. **Implement Components:** Calculator → DataProvider → Formatter → Engine
3. **Run Quality Checks:** `pytest && ruff check . && mypy .`
4. **Update Docs:** Keep README.md as single source of truth
5. **Commit Atomically:** One logical change per commit

## Critical Reminders

- Financial calculation errors = material dollar losses → comprehensive testing required
- Django-native solutions preferred over external dependencies
- Single-user focus = simpler architecture, no multi-tenancy
- Documentation lives in README.md (single source of truth)
- Progressive disclosure: Detailed patterns in `.agent/rules/`, quick reference here

## Quick Reference

**Module API:** `get_presentation_rows(user)`, `get_sidebar_data(user)`, `get_holdings_rows(user, account_id)`

**Test Coverage:** `pytest --cov=portfolio --cov-report=term-missing`

**Type Check:** `mypy portfolio/`

**Format:** `ruff format . && ruff check . --fix`

---

See `.agent/rules/` for detailed architectural patterns, testing strategies, and Django-specific guidelines.

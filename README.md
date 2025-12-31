# cb3portfolio

A Django-based web application for managing multi-account investment portfolios with tax-optimized asset location and automated rebalancing calculations.

## Features

- **Multi-Account Portfolio Management** - Track securities, asset classes, and accounts across multiple tax treatments
- **Allocation Tracking** - Monitor current allocations vs. target strategies at portfolio, account-type, and account levels
- **Tax-Optimized Asset Location** - CVXPY-powered optimization to maximize after-tax returns
- **Rebalancing Calculator** - Generate buy/sell recommendations to restore target allocations
- **Flexible Strategy System** - Define portfolio-wide and per-account/account-type allocation strategies
- **Real-Time Market Data** - Automatic price updates via Yahoo Finance integration
- **Comprehensive Dashboard** - View allocations, variances, and holdings with interactive displays

## Technology Stack

- **Python 3.14+** - Latest stable Python with enhanced type system
- **Django 6.0** - Web framework with native CSP support
- **pandas** - Vectorized financial calculations (10-20x performance improvement)
- **UV** - Fast, modern package manager
- **SQLite** - Development database (PostgreSQL ready for production)
- **CVXPY** - Portfolio optimization engine
- **pytest** - Testing framework with ~94% coverage target
- **structlog** - Structured logging for production observability

## Architecture

cb3portfolio follows **domain-driven design** with a **composition pattern** for service layer calculations.

### Core Principles

1. **Django-Native First** - Use Django's built-in features before adding dependencies
2. **Domain-Driven Design** - Business logic lives in domain models
3. **Composition Pattern** - Services use dependency injection for testability
4. **Comprehensive Testing** - ~94% coverage with golden reference tests for financial calculations
5. **Single-User Focus** - Simplified architecture, no multi-tenancy complexity

### Layer Responsibilities

**Domain Models** (`portfolio/domain/models.py`)
- Business logic and validation
- `Portfolio` - Container for accounts with rollup calculations
- `Account` - Aggregates holdings and calculates drift from targets
- `AllocationStrategy` - Manages target allocations with automatic cash calculation
- **Rule**: Business logic lives here, not in views or services

**Service Layer** (`portfolio/services/allocations/`)
- **Composition Pattern with Dependency Injection**

```
AllocationEngine (orchestration)
  ├── AllocationCalculator (pure pandas calculations)
  ├── DjangoDataProvider (ORM → pandas DataFrames)
  └── AllocationFormatter (DataFrame → dict transformation)
```

**Component Responsibilities:**

1. **Calculator** (`calculations.py`)
   - Pure pandas calculations
   - NO Django dependencies
   - Fully unit testable without database
   - Vectorized operations for 10-20x performance

2. **DataProvider** (`data_providers.py`)
   - All Django ORM queries
   - Converts models to pandas DataFrames
   - Optimized with select_related/prefetch_related
   - Single source of data fetching

3. **Formatter** (`formatters.py`)
   - Transforms DataFrames to template-ready dicts
   - Returns raw numeric values (float/int)
   - NO string formatting (handled by template filters)

4. **Engine** (`engine.py`)
   - Orchestrates the three components
   - Dependency injection for testing
   - Exposes clean public API
   - Handles logging and error handling

**Public API** (`__init__.py`):
```python
from portfolio.services.allocations import get_presentation_rows

# Single clean call in views
rows = get_presentation_rows(user=request.user)
```

**Data Flow:**
```
View → get_presentation_rows(user)
        → AllocationEngine
          → DjangoDataProvider (fetch data from Django ORM)
          → AllocationCalculator (calculate with pandas)
          → AllocationFormatter (transform to dicts)
            → list[dict] with raw floats
              → Template applies |money, |percent filters
```

**Views** (`portfolio/views.py`)
- HTTP request/response handling
- Single service call per view
- **Rule**: No business logic in views

**Templates** (`portfolio/templates/`)
- Display with custom filters for formatting
- `|money` - Format currency ($50,000)
- `|percent` - Format percentages (62.5%)
- **Rule**: Templates display, they don't calculate

### Why This Architecture?

**Why Composition Pattern?**
- Each component testable independently
- Calculator has NO Django dependencies (pure pandas)
- Dependency injection enables mocking
- Maintains clean API for views (single function call)
- More maintainable as complexity grows

**Why Pandas?**
- 10-20x performance improvement via vectorization
- Natural fit for hierarchical portfolio data (MultiIndex)
- Industry standard for financial data analysis
- Clean aggregation and grouping operations

**Why Template Filters for Formatting?**
- Separation of concerns (calculation vs. presentation)
- Template filters are reusable
- Easier to test (verify numbers, not strings)
- Consistent formatting across entire app

Python returns raw values:
```python
return {'value': float(amount)}  # Raw numeric
```

Template formats display:
```django
{{ row.value|money }}  → "$50,000"
{{ row.pct|percent }}  → "62.5%"
```

## Project Structure

```
cb3portfolio/
├── manage.py                    # Django management script
├── pyproject.toml              # UV project configuration & dependencies
├── CLAUDE.md                   # AI assistant quick reference
├── .agent/
│   └── rules/                  # Detailed architectural patterns
│       ├── architecture.md     # Core architectural principles
│       ├── django-patterns.md  # Django-specific patterns
│       └── testing-strategy.md # Testing best practices
├── config/                     # Django project settings
│   ├── settings/
│   │   ├── base.py            # Shared settings
│   │   ├── development.py     # Development environment
│   │   ├── testing.py         # Test environment
│   │   └── production.py      # Production environment
│   ├── logging.py             # Structured logging configuration
│   ├── urls.py                # URL routing
│   └── wsgi.py                # WSGI configuration
├── portfolio/                  # Main Django app
│   ├── domain/                # Domain models & business logic
│   │   └── models.py          # All domain models
│   ├── services/              # Service layer
│   │   └── allocations/       # Allocation calculations (composition pattern)
│   │       ├── __init__.py    # Public API (convenience functions)
│   │       ├── engine.py      # AllocationEngine (orchestration)
│   │       ├── calculations.py # AllocationCalculator (pure pandas)
│   │       ├── data_providers.py # DjangoDataProvider (ORM → DataFrame)
│   │       ├── formatters.py  # AllocationFormatter (DataFrame → dict)
│   │       └── types.py       # TypedDict schemas
│   ├── views.py               # Web views (thin, single service call)
│   ├── urls.py                # App-specific URLs
│   ├── admin.py               # Django admin configuration
│   ├── forms.py               # Form validation
│   ├── templatetags/          # Custom template filters
│   │   └── portfolio_filters.py # |money, |percent filters
│   ├── templates/portfolio/   # HTML templates
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── targets.html
│   │   └── holdings.html
│   └── tests/                 # Test suite (~94% coverage)
│       ├── conftest.py        # Shared pytest fixtures
│       ├── domain/            # Domain model tests
│       ├── services/
│       │   └── allocations/   # Component tests
│       │       ├── test_calculations.py    # Calculator (no Django)
│       │       ├── test_data_providers.py  # DataProvider (with Django)
│       │       ├── test_formatters.py      # Formatter (no Django)
│       │       └── test_engine.py          # Integration tests
│       └── views/             # View and template tests
└── static/                    # Static files (CSS, JS)
```

## Data Models

### Core Models

**Portfolio** - Container for all accounts
- Links to user (single-user application)
- Aggregates account totals
- Provides rollup calculations

**Account** - Individual account (401k, IRA, Taxable, etc.)
- Links to Portfolio
- Has AccountType (defines tax treatment)
- Aggregates holdings
- Can have per-account allocation strategy

**Security** - Individual security (stock, bond, fund)
- Ticker symbol
- Links to AssetClass
- Tracks latest price via SecurityPrice model

**Holding** - Position in an account
- Links Account → Security
- Tracks shares, cost basis
- Calculates current value from latest price

**AssetClass** - Investment category (US Stocks, Bonds, etc.)
- Grouped by AssetClassCategory
- Used for allocation tracking

**AllocationStrategy** - Target allocation definition
- Defines target percentages per asset class
- Can be assigned to portfolio, account types, or individual accounts
- Automatic cash calculation (plug to 100%)

### Allocation Terminology

Three distinct concepts are used throughout:

1. **Actual Allocation** (Current Holdings)
   - What you currently own
   - Calculated from holdings

2. **Policy Target** (Stated Strategy)
   - What your investment policy says you should own
   - Defined in AllocationStrategy

3. **Effective Target** (Weighted Average)
   - Achievable target given account constraints
   - Weighted average of policy targets across accounts
   - Used for rebalancing calculations

### Variance Types

1. **Policy Variance** (Actual - Policy)
   - Purpose: Strategy adherence monitoring
   - Question: "Am I following my investment policy?"

2. **Effective Variance** (Actual - Effective)
   - Purpose: Practical rebalancing
   - Question: "How much do I need to trade?"

## Quick Start

### Prerequisites

- **Python 3.14+** ([download](https://www.python.org/downloads/))
- **UV package manager** ([install guide](https://github.com/astral-sh/uv))

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd cb3portfolio

# Install dependencies with UV
uv pip install -e ".[dev]"

# Set up environment variables
cp .env.example .env
# Edit .env and set SECRET_KEY (generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

# Run migrations
uv run python manage.py migrate

# Create superuser
uv run python manage.py createsuperuser

# Load sample data (optional)
uv run python manage.py seed_dev_data

# Start development server
uv run python manage.py runserver
```

Visit `http://127.0.0.1:8000` to access the application.

### Initial Setup

1. **Access Admin**: Go to http://127.0.0.1:8000/admin and log in
2. **Add Asset Classes**: Create asset classes (e.g., "US Stocks", "Bonds") with categories
3. **Add Securities**: Create securities (ETFs, funds) and assign to asset classes
4. **Add Accounts**: Create accounts (IRA, 401k, Taxable) with tax treatments
5. **Add Holdings**: Enter current positions (security, shares, cost basis)
6. **Define Strategies**: Create allocation strategies with target percentages
7. **View Dashboard**: Navigate to dashboard to see allocations and variances

## Development

### Common Commands

```bash
# Development server
uv run python manage.py runserver

# Database operations
uv run python manage.py makemigrations  # Create migrations
uv run python manage.py migrate         # Apply migrations
uv run python manage.py shell_plus      # Enhanced Django shell

# Create superuser
uv run python manage.py createsuperuser

# Seed sample data
uv run python manage.py seed_dev_data
```

### Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=portfolio --cov-report=html

# Run specific test modules
uv run pytest portfolio/tests/services/allocations/test_calculations.py
uv run pytest portfolio/tests/services/allocations/test_data_providers.py
uv run pytest portfolio/tests/services/allocations/test_formatters.py
uv run pytest portfolio/tests/services/allocations/test_engine.py

# Run tests by type
uv run pytest -m unit           # Unit tests only (fast, no Django)
uv run pytest -m integration    # Integration tests (with Django)
uv run pytest -m "not e2e"      # Skip slow E2E tests

# Run with verbosity
uv run pytest -v --tb=short

# Run specific test
uv run pytest -k "test_calculator_builds_presentation"
```

### Testing Strategy

The project maintains ~94% test coverage with testing at multiple levels:

**Component-Level Testing (Unit Tests)**

*Calculator Tests (No Django)*
```python
def test_calculator():
    """Test calculator in isolation without Django."""
    calc = AllocationCalculator()
    result = calc.build_presentation_dataframe(df, ...)
    assert 'portfolio_actual' in result.columns
```

*DataProvider Tests (With Django)*
```python
@pytest.mark.django_db
def test_data_provider(test_user):
    """Test data provider queries."""
    provider = DjangoDataProvider()
    df = provider.get_holdings_df(test_user)
    assert not df.empty
```

*Formatter Tests (No Django)*
```python
def test_formatter():
    """Test formatter returns raw numerics."""
    formatter = AllocationFormatter()
    rows = formatter.to_presentation_rows(df, ...)
    assert isinstance(rows[0]['portfolio']['actual'], float)
```

**Integration Testing**

```python
@pytest.mark.django_db
def test_engine_integration(test_user):
    """Test full pipeline integration."""
    rows = get_presentation_rows(test_user)
    assert len(rows) > 0
    assert 'portfolio' in rows[0]
```

**Golden Reference Testing**

Financial calculations are validated with real-world portfolio scenarios:

```python
@pytest.mark.django_db
def test_golden_reference_allocation(test_portfolio):
    """
    Test with known portfolio: $80k total
    - US Equities: $50k (62.5%)
    - Bonds: $30k (37.5%)
    Target: 60% equities, 40% bonds
    Expected variance: +2.5% equities, -2.5% bonds
    """
    rows = get_presentation_rows(test_portfolio.user)

    equities = next(r for r in rows if r['asset_class_name'] == 'US Equities')
    assert abs(equities['portfolio']['actual'] - 50000.0) < 0.01
    assert abs(equities['portfolio']['variance_pct'] - 2.5) < 0.01
```

**Why Golden Reference Tests?**
- Financial calculation errors could result in material dollar losses
- Real scenarios catch edge cases that unit tests miss
- Validates entire pipeline, not just individual components
- Provides confidence in production accuracy

### Code Quality

```bash
# Linting
uv run ruff check .              # Check for issues
uv run ruff check . --fix        # Auto-fix issues

# Formatting
uv run ruff format .             # Format all files
uv run ruff format --check .     # Check formatting

# Type checking
uv run mypy portfolio/           # Type check codebase

# Security
uv run ruff check . --select S   # Security checks
uv run safety check              # Dependency vulnerabilities

# Run all checks
uv run ruff check . && uv run ruff format --check . && uv run mypy portfolio/
```

### Pre-Commit Hooks

```bash
# Install pre-commit hooks
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

# Run hooks manually
uv run pre-commit run --all-files

# Hooks include:
# - Ruff linting and formatting
# - Django system checks
# - Django migration checks
# - Fast unit tests (on commit)
# - Integration tests (on push)
# - Safety vulnerability checks (on push)
# - Secret detection
```

## Environment Configuration

### Settings Modules

The application supports three environments:

**Development (Default)**
```bash
DJANGO_SETTINGS_MODULE=config.settings.development
uv run python manage.py runserver
```

**Testing**
```bash
DJANGO_SETTINGS_MODULE=config.settings.testing
uv run pytest
```

**Production**
```bash
DJANGO_SETTINGS_MODULE=config.settings.production
uv run python manage.py check --deploy
```

### Environment Variables

Create a `.env` file in the project root:

```env
# Required
SECRET_KEY=your-secret-key-here
DEBUG=True

# Database (development uses SQLite by default)
DATABASE_URL=sqlite:///db.sqlite3

# Production (example)
# DATABASE_URL=postgresql://user:password@localhost:5432/cb3portfolio  # pragma: allowlist secret
# ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

Generate a SECRET_KEY:
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

### Logging Strategy

The project uses structured logging with `structlog`:

**Configuration**: `config/logging.py`

**Development**: Pretty console output with colors, DEBUG level
**Testing**: Minimal logging (CRITICAL only)
**Production**: JSON-formatted logs with file rotation

**Log Files (production only)**:
- `logs/application.log` - All application logs (INFO+)
- `logs/errors.log` - Error logs only (ERROR+)
- Both use 10MB rotation with 5 backup files

**Customize logging**:
```python
from config.logging import get_logging_config

LOGGING = get_logging_config(debug=False)
# Modify handlers, adjust levels, etc.
```

## Production Deployment

### Pre-Deployment Checklist

1. **Environment Variables**
   ```bash
   SECRET_KEY=<generated-secret-key>
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   DB_NAME=cb3portfolio_prod
   DB_USER=portfolio_user
   DB_PASSWORD=<secure-password>
   DB_HOST=localhost
   DB_PORT=5432
   ```

2. **Database Setup**
   ```bash
   # Create PostgreSQL database
   createdb cb3portfolio_prod

   # Run migrations
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py migrate

   # Create superuser
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py createsuperuser
   ```

3. **Static Files**
   ```bash
   uv run python manage.py collectstatic
   ```

4. **Security Checks**
   ```bash
   uv run python manage.py check --deploy
   uv run ruff check . --select S
   uv run safety check
   ```

### Security Features

- **Django 6.0 Native CSP**: Content Security Policy configured in settings
- **HSTS**: HTTP Strict Transport Security enabled in production
- **Secure Cookies**: Session and CSRF cookies secured in production
- **Secret Scanning**: Pre-commit hook prevents committing secrets
- **Dependency Scanning**: Automated vulnerability checks in CI/CD
- **Security Headers**: Configured via WhiteNoise and Django settings

## CI/CD

GitHub Actions workflows run automatically:

- **CI** (`.github/workflows/ci.yml`): Tests, linting, type checking, coverage
- **Security** (`.github/workflows/security.yml`): Security scanning, vulnerability checks
- **Dependency Review** (`.github/workflows/dependency-review.yml`): PR dependency analysis

## Dependency Management

### Update Strategy

**Security Updates** - Immediate
- Applied immediately via Dependabot PRs
- Automated by GitHub Actions
- Pre-commit safety checks

**Python Version** - Conservative
- Stay within 1 minor version of latest stable
- Currently: Python 3.14+
- Test thoroughly before major version upgrades

**Django** - Quarterly Review
- Update to latest LTS or stable minor within 3 months
- Currently: Django 6.0
- Test thoroughly for major version upgrades

**Libraries** - Monthly
- Review minor/patch updates monthly
- Auto-merge if CI passes
- Manual review for major version updates

### Monitoring

```bash
# Check outdated packages
uv pip list --outdated

# Security audit
uv run safety check

# Update dependencies (development)
uv sync --upgrade
```

## Key Architectural Decisions

### Why Single-User Focus?

- Simpler architecture
- No multi-tenancy complexity
- Faster development iteration
- Personal tool optimization
- Easier testing

### Why Use Decimal for Money?

- Avoids floating-point precision errors
- Ensures exact decimal arithmetic
- Industry best practice for monetary values
- Convert to `float` only at template boundary

### Why Progressive Disclosure in Documentation?

- **CLAUDE.md**: Quick reference, common commands
- **.agent/rules/**: Detailed patterns for AI assistants
- **README.md**: Comprehensive documentation (single source of truth)
- Prevents documentation drift
- Easy to maintain

### Why ~94% Test Coverage Target?

- Financial calculations could result in material losses
- Comprehensive testing provides confidence
- Golden reference tests catch real-world edge cases
- Not 100% because some code is intentionally untested (e.g., Django migrations)

## Contributing

### Development Workflow

1. Create feature branch
2. Make changes
3. Write/update tests
4. Run quality checks: `uv run ruff check . && uv run mypy portfolio/`
5. Run tests: `uv run pytest`
6. Commit (pre-commit hooks will run)
7. Create pull request

### Code Style

- Follow PEP 8 (enforced by Ruff)
- Use type hints for all function signatures
- Write docstrings for public functions
- Keep functions focused and small
- Use Django conventions and idioms
- Prefer Django-native solutions

### Adding Dependencies

```bash
# Production dependency
uv add package-name

# Development dependency
uv add --dev package-name

# Update lock file
uv lock
```

## License

[Your License Here]

## Support

For questions or issues:
- Check CLAUDE.md for quick reference
- Review .agent/rules/ for detailed patterns
- Open an issue on GitHub

## Acknowledgments

Built with:
- **Django** - Web framework
- **pandas** - Data manipulation and vectorized calculations
- **CVXPY** - Portfolio optimization engine
- **UV** - Fast package manager
- **pytest** - Testing framework
- **structlog** - Structured logging

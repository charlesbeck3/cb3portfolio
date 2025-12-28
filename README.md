# Portfolio Management Platform

A Django-based web application for managing multi-account investment portfolios with tax-optimized asset location and automated rebalancing.

## Features

- **Asset & Account Management** - Track securities, asset classes, and accounts via Django admin
- **Tax-Optimized Asset Location** - CVXPY-powered optimization to maximize after-tax returns
- **Rebalancing Calculator** - Generate buy/sell recommendations to restore target allocations
- **Portfolio Dashboard** - View current allocations vs. targets

## Technology Stack

- **Python 3.12+** - Latest stable Python
- **Django 5.1** - Web framework with built-in admin
- **UV** - Fast, modern package manager
- **SQLite** - Development database
- **CVXPY** - Portfolio optimization engine
- **NumPy & Pandas** - Data manipulation

## Architecture

cb3portfolio follows domain-driven design principles with clear separation of concerns:

### Layer Responsibilities

- **Domain Models** (`portfolio/models.py`) - Business logic and validation
  - `AllocationStrategy` - Manages target allocations with automatic cash calculation
  - `Account` - Aggregates holdings and calculates drift from targets
  - `Portfolio` - Container for accounts with rollup calculations
  - **Rule**: Business logic lives here, not in views or services

- **Services** (`portfolio/services/`) - Orchestration and aggregation
  - `AllocationCalculationEngine` - Portfolio-wide calculation orchestration
  - `AllocationPresentationFormatter` - Formats data for templates
  - **Rule**: Services orchestrate domain models, they don't duplicate business logic

- **Forms** (`portfolio/forms/`) - User input validation
  - Validate user input before passing to domain models
  - **Rule**: Forms validate, domain models enforce business rules

- **Views** (`portfolio/views/`) - Presentation and HTTP handling
  - Handle HTTP requests/responses
  - Call services and domain models
  - **Rule**: No business logic in views

- **Templates** - Display only (no business logic)
  - Render data provided by views
  - **Rule**: Templates display, they don't calculate

### Allocation Terminology

Standardized naming is used throughout the application to distinguish between three concepts:

1.  **Actual Allocation** (Current Holdings)
    - **What it is**: Current dollar and percentage allocation based on actual holdings.
    - **Use case**: Shows what you currently own.

2.  **Policy Target** (Stated Strategy)
    - **What it is**: Target allocation percentage assigned in an `AllocationStrategy`.
    - **Use case**: Shows what the investment policy says you should own.

3.  **Effective Target** (Weighted Average)
    - **What it is**: The weighted average of policy targets across all accounts.
    - **Use case**: Shows the achievable target given account constraints and individual strategies. Useful for rebalancing.

### Variance Concepts

1.  **Policy Variance** (Actual - Policy)
    - **Purpose**: Strategy adherence monitoring - "Am I following my investment policy?"

2.  **Effective Variance** (Actual - Effective)
    - **Purpose**: Practical rebalancing - "How much do I need to trade to hit my targets?"

### Naming Conventions

The calculation engine uses a standardized suffix pattern for DataFrame columns:

- `{prefix}_actual`: Current holdings (dollars)
- `{prefix}_actual_pct`: Current holdings (percentage)
- `{prefix}_policy`: Policy target (dollars)
- `{prefix}_policy_pct`: Policy target (percentage)
- `{prefix}_policy_variance`: actual - policy (dollars)
- `{prefix}_effective`: Weighted average target (dollars)
- `{prefix}_effective_pct`: Weighted average target (percentage)
- `{prefix}_effective_variance`: actual - effective (dollars)

### Key Principles

1. **Single Source of Truth** - Business logic lives in domain models
2. **DRY** - No duplicate calculation logic across layers
3. **Trust the Database** - Domain models ensure data integrity
4. **Clear Boundaries** - Each layer has specific responsibilities

### Cash Allocation Pattern

Cash is treated as a first-class asset class with flexible handling:

- Users can explicitly provide cash allocation (must sum to 100%)
- Users can omit cash and it's auto-calculated as the plug
- All cash allocations are stored in the database
- `AllocationStrategy.save_allocations()` is the single source of truth
- `AllocationStrategy.calculate_cash_allocation()` contains the isolated cash calculation logic

**Business Rule:** Cash percentage = 100% - sum(all other allocations)

**Example:**
```python
# Implicit cash (auto-calculated)
strategy.save_allocations({
    stocks_id: Decimal("60.00"),
    bonds_id: Decimal("30.00")
})  # Cash = 10%

# Explicit cash (validated)
strategy.save_allocations({
    stocks_id: Decimal("60.00"),
    bonds_id: Decimal("30.00"),
    cash_id: Decimal("10.00")
})  # Must sum to exactly 100%
```

## Quick Start

### Prerequisites

- Python 3.12 or higher
- UV package manager ([install guide](https://github.com/astral-sh/uv))

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd portfolio-management

# Install dependencies with UV
uv pip install -e ".[dev]"

# Create environment file
cp .env.example .env
# Edit .env and set SECRET_KEY (generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

# Run migrations
uv run python manage.py migrate

# Create superuser for admin access
uv run python manage.py createsuperuser

# Run development server
uv run python manage.py runserver

# (Optional) Seed development data
# Creates a demo user with a realistic portfolio
uv run python manage.py seed_dev_data

```

Access the application at http://127.0.0.1:8000/

### First Steps

1. **Access Admin**: Go to http://127.0.0.1:8000/admin and log in
2. **Add Asset Classes**: Create asset classes (e.g., "US Stocks", "Bonds") with target allocations
3. **Add Securities**: Create securities (ETFs, funds) and assign to asset classes
4. **Add Accounts**: Create accounts (IRA, 401k, Taxable) with tax treatments
5. **Add Holdings**: Enter current positions (security, shares, cost basis)
6. **Run Optimization**: Navigate to optimization view to calculate optimal asset location
7. **View Rebalancing**: Check rebalancing view for trade recommendations

## Project Structure

```
portfolio_management/
├── manage.py                    # Django management script
├── pyproject.toml              # UV project configuration
├── .env                        # Environment variables (create from .env.example)
├── .cursorrules                # Cursor AI configuration
├── README.md                   # This file
├── config/                     # Django project settings
│   ├── __init__.py
│   ├── settings.py            # Main settings file
│   ├── urls.py                # URL routing
│   └── wsgi.py                # WSGI configuration
├── portfolio/                  # Main Django app
│   ├── models/                # Domain models package
│   │   ├── __init__.py        # Exports all models
│   │   ├── accounts.py        # Account-related models
│   │   ├── assets.py          # Asset class models
│   │   ├── portfolio.py       # Portfolio container
│   │   ├── securities.py      # Security and Holding models
│   │   └── strategies.py      # Allocation strategies
│   ├── admin.py               # Django admin configuration
│   ├── views.py               # Web views
│   ├── urls.py                # App-specific URLs
│   ├── services/              # Business logic layer
│   │   ├── __init__.py
│   │   ├── optimization.py    # CVXPY asset location optimizer
│   │   └── rebalancing.py     # Rebalancing calculator
│   ├── templates/portfolio/   # HTML templates
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── optimization.html
│   │   └── rebalancing.html
│   └── tests/                 # Test suite
│       ├── __init__.py
│       ├── models/            # Model tests
│       ├── views/             # View tests
│       ├── services/          # Service tests
│       ├── calculations/      # Financial math tests
│       └── e2e/               # Browser tests
├── static/                    # Static files
│   └── css/                   # Stylesheets
│       └── portfolio.css      # Main application styles
└── db.sqlite3                  # SQLite database (created on first run)
```

## Data Models

### Core Models

- **AssetClass** - Investment categories (US Stocks, Bonds, etc.)
  - Defines target allocation percentages
  - Expected returns and volatility for optimization

- **Security** - Individual investments (ETFs, mutual funds, stocks)
  - Linked to asset class
  - Tax efficiency ratings for optimization

- **Account** - Investment accounts (IRA, 401k, Taxable, etc.)
  - Tax treatment (tax-deferred, tax-free, taxable)
  - Institution and account details

- **Holding** - Current portfolio positions
  - Links account, security, shares, cost basis
  - Tracks current value and unrealized gains/losses

- **TargetAllocationByAccount** - Optimized allocations
  - Tax-efficient allocation per asset class per account
  - Generated by optimization engine

- **RebalancingRecommendation** - Trade recommendations
  - Buy/sell recommendations to restore targets
  - Includes rationale and estimated amounts

## Key Features

### Asset Location Optimization

Uses CVXPY to determine optimal placement of asset classes across accounts to maximize after-tax returns.

**Algorithm:**
- Objective: Maximize after-tax portfolio returns
- Constraints:
  - Overall portfolio matches target allocation
  - Each account is fully invested
  - No short positions
  - Tax-deferred accounts prefer bonds (tax inefficient)
  - Taxable accounts prefer stocks (tax efficient)

**Usage:**
```python
from portfolio.services.optimization import optimize_asset_location

accounts = Account.objects.all()
asset_classes = AssetClass.objects.all()

results = optimize_asset_location(accounts, asset_classes)
# Returns: {'Roth IRA': {'Stocks': 80.0, 'Bonds': 20.0}, ...}
```

### Rebalancing Calculator

Generates buy/sell recommendations to restore portfolio to target allocations.

**Algorithm:**
1. Calculate current allocation per account
2. Compare to target allocations
3. Identify securities to buy/sell
4. Minimize transaction count
5. Consider tax implications

**Usage:**
```python
from portfolio.services.rebalancing import calculate_rebalancing

account = Account.objects.get(name='Roth IRA')
threshold = 0.05  # 5% rebalancing threshold

trades = calculate_rebalancing(account, threshold)
# Returns list of Trade objects with security, action, shares, amount
```

## Development

### Running Tests

```bash
# Run all tests
uv run python manage.py test

# Run specific test file
uv run python manage.py test portfolio.tests.test_optimization

# Run with coverage
uv run coverage run --source='.' manage.py test
uv run coverage report
```

### Code Quality

```bash
# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Run both
uv run ruff check . && uv run ruff format .

### Pre-Commit Hooks
This project uses pre-commit to ensure code quality before committing.

```bash
# Install hooks (run once)
uv run pre-commit install

# Run hooks manually
uv run pre-commit run --all-files
```
```

### Database Operations

```bash
# Create migrations after model changes
uv run python manage.py makemigrations

# Apply migrations
uv run python manage.py migrate

# Access Django shell
uv run python manage.py shell

# Access database shell
uv run python manage.py dbshell
```

### Adding Dependencies

```bash
# Add production dependency
uv add package-name

# Add development dependency
uv add --dev package-name

# Update all dependencies
uv pip install --upgrade -e ".[dev]"
```

## Common Commands

```bash
# Development server
uv run python manage.py runserver

# Create superuser
uv run python manage.py createsuperuser

# Make migrations
uv run python manage.py makemigrations

# Apply migrations
uv run python manage.py migrate

# Seed development data
uv run python manage.py seed_dev_data

# Run tests
uv run python manage.py test

# Django shell
uv run python manage.py shell

# Lint and format
uv run ruff check . && uv run ruff format .
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

### Production Environment Variables

Required for production deployment:
- `SECRET_KEY` - Django secret key (generate with `get_random_secret_key()`)
- `ALLOWED_HOSTS` - Comma-separated list of allowed hostnames
- `DB_NAME`, `DB_USER`, `DB_PASSWORD` - PostgreSQL credentials
- Email settings (optional but recommended for error reporting)

See `.env.example` for complete list.

### Logging Strategy

The project uses structured logging with `structlog` for both development and production:

**Configuration Location**: All logging configuration lives in `config/logging.py`

- **Development**: Pretty console output with colors, DEBUG level for portfolio app
- **Testing**: Minimal logging (CRITICAL only) to keep test output clean
- **Production**: JSON-formatted logs with file rotation and email alerts

**Log Files** (production only):
- `logs/application.log` - All application logs (INFO and above)
- `logs/errors.log` - Error logs only (ERROR and above)
- Both use 10MB rotation with 5 backup files

**Customizing Logging**:

Each environment's settings file can customize logging by importing and modifying the base config:

```python
from config.logging import get_logging_config

LOGGING = get_logging_config(debug=False)
# Add custom handlers, adjust levels, etc.
LOGGING["loggers"]["myapp"]["level"] = "DEBUG"
```

**Log Hierarchy**:
- `portfolio` - Main application logger
- `portfolio.services` - Service layer operations
- `portfolio.views` - View layer operations
- `django.request` - HTTP request/response logging
- `django.security` - Security-related events

### Security Hardening

The project includes several security measures and audits:

- **Automated Security Scanning**: GitHub Actions workflow runs Ruff S-rules and `safety` checks on every push/PR and weekly.
- **Secret Scanning**: `detect-secrets` pre-commit hook prevents committing sensitive information.
- **Production Security**: Security settings (HSTS, SSL redirect, secure cookies) are enabled in `config/settings/production.py`.
- **Content Security Policy (CSP)**: Django 6.0 native CSP configured in `config/settings/base.py`
  - Development: Report-only mode (logs violations without blocking)
  - Production: Enforcing mode (blocks violations)
  - Allows Bootstrap CDN, prevents clickjacking, restricts inline scripts
- **Dependency Management**:
    - **Vulnerability Scanning**: `safety` checks for known vulnerabilities (run with `uv run safety check`).
    - **Automated Updates**: GitHub Actions dependency review on all PRs.
    - **Pre-commit Checks**: `safety` runs automatically on pre-push.

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
```

Generate a SECRET_KEY:
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

### Settings

Key settings in `config/settings.py`:
- `DEBUG` - Set to False in production
- `ALLOWED_HOSTS` - Configure for production deployment
- `DATABASES` - SQLite for development, PostgreSQL for production
- `INSTALLED_APPS` - Includes django-debug-toolbar for development

## Architecture Decisions

## Deployment

### Pre-Deployment Checklist

Before deploying to production, ensure:

1. **Environment Variables Set**
   ```bash
   # Required variables
   SECRET_KEY=<generated-secret-key>
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   DB_NAME=cb3portfolio_prod
   DB_USER=portfolio_user
   DB_PASSWORD=<secure-password>
   DB_HOST=localhost
   DB_PORT=5432

   # Optional but recommended
   EMAIL_HOST=smtp.example.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=noreply@yourdomain.com
   EMAIL_HOST_PASSWORD=<app-password>
   ADMIN_EMAIL=admin@yourdomain.com
   ```

2. **Database Setup**
   ```bash
   # Create PostgreSQL database
   createdb cb3portfolio_prod

   # Run migrations
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py migrate

   # Create superuser
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py createsuperuser

   # Seed system data
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py seed_dev_data
   ```

3. **Static Files**
   ```bash
   # Collect static files for serving
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py collectstatic --noinput
   ```

4. **Security Checks**
   ```bash
   # Run Django deployment checks
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py check --deploy

   # Run system checks
   DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py check
   ```

### Production Deployment Steps

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd cb3portfolio
   ```

2. **Install Dependencies**
   ```bash
   uv sync --frozen
   ```

3. **Configure Environment**
   - Copy `.env.example` to `.env`
   - Set all required environment variables
   - Ensure `DEBUG=False`
   - Ensure `DJANGO_SETTINGS_MODULE=config.settings.production`

4. **Initialize Database**
   ```bash
   uv run python manage.py migrate
   uv run python manage.py seed_dev_data  # Creates system data
   uv run python manage.py createsuperuser
   ```

5. **Collect Static Files**
   ```bash
   uv run python manage.py collectstatic --noinput
   ```

6. **Start Application**
   ```bash
   # Using gunicorn (recommended for production)
   uv add gunicorn
   uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4

   # Or using uvicorn for ASGI (async support)
   uv add uvicorn
   uv run uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers 4
   ```

### Monitoring & Maintenance

**Health Check Endpoint**
- URL: `/health/`
- Returns JSON status of database connectivity
- Use for load balancer health checks
- Returns 200 OK when healthy, 503 when unhealthy

Example response:
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "version": "1.0.0"
  }
}
```

**Log Locations** (production):
- Application logs: `logs/application.log`
- Error logs: `logs/errors.log`
- Both rotate at 10MB with 5 backups
- JSON format for log aggregation tools

**Performance Monitoring**
- Response headers include `X-Request-ID` for tracing
- Response headers include `X-Request-Duration` for timing
- Slow requests (>0.5s in production) logged automatically with context:
  ```json
  {
    "event": "slow_request_detected",
    "duration": 1.234,
    "path": "/dashboard/",
    "method": "GET",
    "request_id": "abc-123-def",
    "threshold": 0.5
  }
  ```

**Request Tracing**
- Every request has unique `X-Request-ID` in response headers
- Load balancers can inject `X-Request-ID` for end-to-end tracing
- All logs include `request_id` field for correlation
- Use request ID to trace single request through all log entries:
  ```bash
  grep "request_id\":\"abc-123-def" logs/application.log
  ```

**Database Backups**
```bash
# Backup database
pg_dump cb3portfolio_prod > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore database
psql cb3portfolio_prod < backup_20240101_120000.sql
```

**Dependency Updates**
```bash
# Check for security vulnerabilities
uv run safety check

# Update dependencies (test thoroughly before deploying)
uv sync --upgrade
```

### Troubleshooting Production Issues

**Check Application Status**
```bash
# Visit health check endpoint
curl https://yourdomain.com/health/

# Check system status
uv run python manage.py check

# Check deployment readiness
uv run python manage.py check --deploy
```

**View Logs**
```bash
# Application logs (JSON format)
tail -f logs/application.log

# Error logs only
tail -f logs/errors.log

# Filter by request ID
grep "request_id\":\"abc-123-def" logs/application.log

# View logs with jq for better formatting
tail -f logs/application.log | jq .
```

**Common Issues**

*Missing Environment Variables*
- Error: `ImproperlyConfigured: Missing required environment variables`
- Solution: Check `.env` file has all required variables from `.env.example`
- Verify: `printenv | grep DB_`

*Database Connection Failed*
- Check health endpoint: `curl http://localhost:8000/health/`
- Verify database credentials in `.env`
- Test connection: `uv run python manage.py dbshell`
- Check PostgreSQL is running: `systemctl status postgresql`

*Static Files Not Loading*
- Run: `uv run python manage.py collectstatic --noinput`
- Verify `STATIC_ROOT` directory exists
- Check nginx/Apache static file configuration

*Slow Performance*
- Check `logs/application.log` for slow request warnings
- Use `X-Request-Duration` header to identify bottlenecks
- Review database query counts with Django Debug Toolbar in development
- Consider adding database indexes for frequently queried fields

*System Check Warnings*
- Warning: "No asset classes defined in the database"
- Solution: `uv run python manage.py seed_dev_data`
- This creates required system data (asset classes, account types, etc.)

## Performance Optimization

### Database Query Optimization

**Use select_related for foreign keys:**
```python
# Bad: N+1 queries
accounts = Account.objects.all()
for account in accounts:
    print(account.portfolio.name)  # Extra query per account

# Good: Single query with JOIN
accounts = Account.objects.select_related('portfolio').all()
for account in accounts:
    print(account.portfolio.name)  # No extra queries
```

**Use prefetch_related for reverse relations:**
```python
# Bad: N+1 queries
portfolios = Portfolio.objects.all()
for portfolio in portfolios:
    for account in portfolio.accounts.all():  # Extra query per portfolio
        print(account.name)

# Good: Two queries total
portfolios = Portfolio.objects.prefetch_related('accounts').all()
for portfolio in portfolios:
    for account in portfolio.accounts.all():  # No extra queries
        print(account.name)
```

### Database Indexes

The application uses database indexes on frequently queried fields:
- `Account.portfolio` - Foreign key lookups
- `Holding.account` - Portfolio aggregations
- `Security.ticker` - Symbol lookups
- `AssetClass.name` - Allocation matching

Add custom indexes if experiencing slow queries:
```python
class Meta:
    indexes = [
        models.Index(fields=['field_name']),
        models.Index(fields=['field1', 'field2']),  # Composite index
    ]
```

Run migrations after adding indexes:
```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

### Caching Strategies

**Template fragment caching:**
```django
{% load cache %}
{% cache 3600 portfolio_summary portfolio.id %}
    <!-- Expensive template rendering -->
{% endcache %}
```

**View caching:**
```python
from django.views.decorators.cache import cache_page

@cache_page(60 * 15)  # Cache for 15 minutes
def dashboard_view(request):
    # ...
```

**Database connection pooling** (already configured in production):
- `CONN_MAX_AGE = 600` - Reuse connections for 10 minutes
- `CONN_HEALTH_CHECKS = True` - Verify connection health
- Reduces overhead of establishing database connections

### Monitoring Slow Requests

Requests exceeding the threshold are automatically logged:

**Development:** Threshold = 1.0 seconds
**Production:** Threshold = 0.5 seconds

Log format:
```json
{
  "event": "slow_request_detected",
  "duration": 1.234,
  "path": "/dashboard/",
  "method": "GET",
  "request_id": "abc-123-def",
  "threshold": 0.5,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

To adjust the threshold, set `SLOW_REQUEST_THRESHOLD` in settings:
```python
# config/settings/production.py
SLOW_REQUEST_THRESHOLD = 0.3  # 300ms
```

### Production Performance Checklist

- [ ] Database indexes on foreign keys and frequently queried fields
- [ ] `select_related()` used for foreign key queries
- [ ] `prefetch_related()` used for reverse relations
- [ ] Template caching for expensive renders
- [ ] Static files compressed and cached (Whitenoise configured)
- [ ] Database connection pooling enabled (CONN_MAX_AGE)
- [ ] Slow request monitoring active (SLOW_REQUEST_THRESHOLD)
- [ ] gunicorn/uvicorn with multiple workers
- [ ] Regular database VACUUM and ANALYZE (PostgreSQL)

### Why Django?
- Built-in admin interface (zero UI code for CRUD)
- Strong ORM for relational data
- Excellent documentation and ecosystem
- Easy to extend and maintain

### Why CVXPY?
- Purpose-built for convex optimization
- Natural syntax for portfolio constraints
- Handles complex optimization problems efficiently
- Better than general-purpose scipy.optimize for this use case

### Why SQLite Initially?
- Zero configuration setup
- Perfect for single-user applications
- Easy migration to PostgreSQL when needed
- File-based for simple backups

### Why UV?
- 10-100x faster than pip
- Modern dependency management
- Automatic virtual environment handling
- Better dependency resolution

### Constants and Configuration

The application uses constants defined directly on domain models, not in separate files.
This follows Django conventions and Domain-Driven Design principles.

#### Naming Conventions

1. **Entity Name Constants**: `{DESCRIPTOR}_NAME = "Value"`
2. **Choice Constants**: `{CHOICE_VALUE} = "DB_VALUE"`
3. **Numeric Constants**: `{DESCRIPTOR}_{UNIT}`
4. **Helper Methods**: `get_{descriptor}()` and `is_{descriptor}()`

#### Usage Examples

```python
# Check if asset class is Cash
if asset_class.is_cash():
    # Special handling for cash

# Get Cash asset class (cached)
cash = AssetClass.get_cash()

# Use numeric constants
if total != AllocationStrategy.TOTAL_ALLOCATION_PCT:
    raise ValidationError(...)
```

### Numeric Precision Strategy

The application uses a hybrid approach for numeric precision to balance accuracy and performance:

1.  **Domain Models & Database**: Use `Decimal` for all financial values to ensure exact precision for storage and validation.
    -   Currency fields: `DecimalField(max_digits=20, decimal_places=2)` for standard values, up to 8 places for shares/crypto.
    -   Percentage fields: `DecimalField` for exact target representation.

2.  **Calculation Service**: Uses `float` (via Pandas `float64`) for heavy portfolio aggregations and analysis.
    -   **Reasoning**: Pandas offers significantly higher performance and richer vectorization support with native floats compared to Python `Decimal` objects.
    -   **Trade-off**: Acceptable micro-variance (e.g., `1e-9`) in intermediate calculations is tolerated.
    -   **Mitigation**: Final presentation values are rounded/formatted for display, masking floating-point artifacts. Tests verify that error margins remain negligible.

## Future Enhancements

**Not in MVP - Add Later:**
- Transaction history tracking
- Historical performance analysis
- Interactive charts (Chart.js or Plotly)
- Multi-user support with authentication
- PostgreSQL migration for production
- Background job processing (Django-Q2)
- API endpoints (Django REST Framework)
- Tax-loss harvesting automation
- Broker integrations for data import

## Testing

### Test Organization

Tests are organized by type and complexity:

**Unit Tests** - Pure logic, no database
- `services/test_allocations.py`: Pandas calculation engine
- Run with: `uv run pytest -m unit`

**Integration Tests** - Database required
- `models/`: Model validation and ORM
- `views/`: View logic and HTTP responses
- `services/`: Domain model business logic & services
- Run with: `uv run pytest -m integration`

**E2E Tests** - Browser automation
- `e2e/`: Playwright browser tests
- Run with: `uv run pytest -m e2e`

**Golden Reference Tests** - Known expected values
- `calculations/test_golden_reference.py`: Real portfolio scenarios
- Run with: `uv run pytest -m golden`

**Performance Tests** - Benchmarks
- `services/test_allocations.py`: Calculation engine performance
- Run with: `uv run pytest -m performance`

### Test Fixtures

#### Available Fixtures (pytest)

**System Data:**
- `base_system_data`: All seeded data (account types, asset classes, securities)

**Users & Portfolios:**
- `test_user`: Standard test user
- `test_portfolio`: Empty portfolio with user
- `simple_holdings`: Portfolio with $1000 VTI in Roth IRA
- `multi_account_holdings`: Roth + Taxable accounts

**Price Mocks:**
- `stable_test_prices`: Standard prices (VTI: $100, BND: $80, etc.)
- `mock_market_prices`: Factory for custom prices
- `zero_prices`: Empty prices for edge cases
- `volatile_prices`: Extreme prices for stress testing

#### Writing New Tests

**Pytest Style (Preferred):**
```python
import pytest
from decimal import Decimal

@pytest.mark.django_db
@pytest.mark.views
def test_dashboard(client, simple_holdings, stable_test_prices):
    client.force_login(simple_holdings['user'])
    response = client.get('/dashboard/')
    assert response.status_code == 200
```

**Django TestCase Style:**
```python
from django.test import TestCase
from portfolio.tests.base import PortfolioTestMixin
from portfolio.tests.fixtures.mocks import MockMarketPrices, get_standard_prices

class MyTest(TestCase, PortfolioTestMixin):
    def setUp(self):
        self.setup_system_data()
        self.user = User.objects.create_user(username="testuser")
        self.create_portfolio(user=self.user)

    def test_something(self):
        with MockMarketPrices(get_standard_prices()):
            # test code
```

### Running Tests

```bash
# All tests
uv run pytest

# By marker
uv run pytest -m unit              # Unit tests only
uv run pytest -m calculations      # Calculation tests
uv run pytest -m "not slow"        # Skip slow tests
uv run pytest -m "views or models" # Multiple markers

# Specific file or test
uv run pytest portfolio/tests/views/test_dashboard.py
uv run pytest portfolio/tests/models/test_accounts.py::TestAccount

# With coverage
uv run pytest --cov=portfolio --cov-report=html
```

### Test Coverage Goals
- Models: 100% (validation, computed properties)
- Services: >80% (optimization, calculation logic)
- Views: >60% (HTTP responses, form handling)

### Troubleshooting Tests

**"setup_portfolio_data not found"**
- Fix: Change to `self.setup_system_data()`

**"MockMarketPrices not defined"**
- Fix: Add `from portfolio.tests.fixtures.mocks import MockMarketPrices`

**Prices not mocked correctly**
- Fix: Ensure `with MockMarketPrices(...):` wraps the view call

## Troubleshooting

### Common Issues

**CVXPY solver fails:**
- Check constraints aren't contradictory
- Verify allocations sum to account values
- Ensure no negative allocations

**N+1 query problems:**
- Use `select_related()` for foreign keys
- Use `prefetch_related()` for reverse relations
- Check django-debug-toolbar SQL panel

**Migrations conflict:**
- Delete migration files and recreate
- Reset database: `rm db.sqlite3 && python manage.py migrate`

**Import errors:**
- Ensure virtual environment is activated
- Run `uv pip install -e ".[dev]"`

## Development Commands

The project uses `uv` for dependency management. All commands use `uv run` prefix:

### Testing
```bash
uv run pytest                                    # Run all tests
uv run pytest --cov=portfolio                    # With coverage
uv run pytest --cov=portfolio --cov-report=html  # HTML coverage report
uv run pytest -m unit                            # Unit tests only
uv run pytest -m integration                     # Integration tests only
```

### Code Quality
```bash
uv run ruff check .                              # Lint
uv run ruff format .                             # Format
uv run ruff check . --fix                        # Auto-fix linting issues
uv run mypy portfolio/                           # Type checking

# Run all checks before committing
uv run ruff check . && uv run ruff format --check . && uv run mypy portfolio/
```

### Security
```bash
uv run ruff check . --select S                   # Security checks
uv run safety check                              # Dependency vulnerabilities
```

### Django Management
```bash
uv run python manage.py runserver                # Start dev server
uv run python manage.py makemigrations           # Create migrations
uv run python manage.py migrate                  # Apply migrations
uv run python manage.py createsuperuser          # Create admin user
```

### Pre-commit Hooks
```bash
# Install pre-commit hooks
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

# Run hooks manually
uv run pre-commit run --all-files
```

## CI/CD

GitHub Actions workflows automatically run on push and PR:

- **CI** (`.github/workflows/ci.yml`): Tests, linting, type checking, coverage
- **Security** (`.github/workflows/security.yml`): Security scanning, vulnerability checks
- **Dependency Review** (`.github/workflows/dependency-review.yml`): Automated dependency analysis on PRs

## Dependency Management Policy

### Update Strategy

The project follows a structured approach to dependency updates:

**Security Updates** (Immediate)
- Applied immediately via Dependabot PRs
- Automated by GitHub Actions dependency review
- Pre-commit `safety` check prevents vulnerable packages

**Python Version** (Conservative)
- Stay within 1 minor version of latest stable Python
- Currently: Python 3.12+ (will upgrade to 3.13 within 6 months of release)
- Major version upgrades require testing period

**Django & Core Framework** (Quarterly Review)
- Django: Update to latest LTS or stable minor within 3 months
- Major version upgrades planned with adequate testing period
- Currently: Django 6.0

**Library Updates** (Monthly Cadence)
- Review minor/patch updates monthly
- Auto-merge if CI passes and no breaking changes
- Major version updates require manual review

### Update Workflow

1. **Dependabot PRs**: Auto-created for security and version updates
2. **CI Validation**: All tests must pass before merge
3. **Dependency Review**: GitHub Actions checks for vulnerabilities
4. **Manual Testing**: Complex updates tested in development first

### Monitoring

```bash
# Check for outdated packages
uv pip list --outdated

# Security audit
uv run safety check

# Update all dependencies (development)
uv sync --upgrade
```

### Pinning Strategy

- **Production**: Use exact versions in `pyproject.toml` for reproducibility
- **Development**: Allow minor/patch updates for faster iteration
- **CI**: Use locked versions from `uv.lock` for consistency

## Contributing

### Development Workflow

1. Create feature branch
2. Make changes
3. Write/update tests
4. Run checks: `uv run check`
5. Run tests: `uv run test`
6. Commit changes (pre-commit hooks will run)
7. Create pull request

### Code Style

- Follow PEP 8 (enforced by Ruff)
- Use type hints for function signatures
- Write docstrings for public functions
- Keep functions focused and small
- Use Django conventions and idioms

## License

[Your License Here]

## Support

For questions or issues:
- Check documentation in docs/
- Review .cursorrules for AI assistant guidance
- Open an issue on GitHub

## Acknowledgments

Built with:
- Django - Web framework
- CVXPY - Optimization engine
- UV - Package manager
- NumPy & Pandas - Data manipulation

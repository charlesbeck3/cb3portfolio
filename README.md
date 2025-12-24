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
│   ├── models.py              # Data models (AssetClass, Security, Account, etc.)
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
│       ├── test_models.py
│       ├── test_optimization.py
│       └── test_rebalancing.py
├── static/                     # Static files (CSS, JS)
│   └── css/
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

# Run tests
uv run python manage.py test

# Django shell
uv run python manage.py shell

# Lint and format
uv run ruff check . && uv run ruff format .
```

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

## Testing Strategy

### Test Coverage Goals
- Models: 100% (validation, computed properties)
- Services: >80% (optimization, rebalancing logic)
- Views: >60% (basic rendering, form handling)

### Test Types
- Unit tests for business logic (services/)
- Integration tests for database operations
- View tests for HTTP responses
- Model tests for validation

### Running Tests
```bash
# All tests
uv run python manage.py test

# Specific app
uv run python manage.py test portfolio

# With verbosity
uv run python manage.py test --verbosity=2

# Keep test database
uv run python manage.py test --keepdb
```

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

## Contributing

### Development Workflow

1. Create feature branch
2. Make changes
3. Write/update tests
4. Run linter: `uv run ruff check . && uv run ruff format .`
5. Run tests: `uv run python manage.py test`
6. Commit changes
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
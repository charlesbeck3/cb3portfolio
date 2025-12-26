# Portfolio Management Platform - Cursor Rules

## Project Overview
You are helping build a Django-based portfolio management platform for tax-optimized investment portfolio management. The platform manages multi-account portfolios with asset location optimization and rebalancing calculations.

## Core Technology Stack
- **Python 3.12+** - Latest stable Python
- **Django 5.1.x** - Web framework with admin interface
- **UV** - Package manager (fast, modern alternative to pip)
- **SQLite** - Database (migrate to PostgreSQL later if needed)
- **CVXPY** - Portfolio optimization engine
- **NumPy & Pandas** - Data manipulation
- **HTML Tables** - Initial UI (defer charts until needed)

## Project Philosophy
- **Start Simple:** MVP with minimal dependencies
- **Incremental Development:** Build, test, and verify one component at a time
- **Django Admin First:** Leverage built-in admin for data entry
- **Tables Before Charts:** Validate logic before adding visualization
- **Defer Premature Optimization:** Add complexity only when needed
- **No Async Yet:** Keep synchronous until performance requires it

## Code Style & Standards

### Python Style
- Use **Ruff** for linting and formatting (configured in pyproject.toml)
- Line length: 100 characters
- Python 3.12+ type hints preferred
- Docstrings for all public functions and classes
- Use double quotes for strings

### Django Conventions
- Follow Django's project structure conventions
- Use Django's built-in features before adding libraries
- Class-based views for CRUD, function-based for custom logic
- Keep business logic in services/ directory, not views
- Use Django ORM efficiently (select_related, prefetch_related)

### Naming Conventions
- Models: PascalCase (e.g., `AssetClass`, `TargetAllocationByAccount`)
- Functions/methods: snake_case (e.g., `calculate_allocation`, `optimize_location`)
- Constants: UPPER_SNAKE_CASE (e.g., `TAX_DEFERRED`, `MAX_ALLOCATION_PCT`)
- File names: snake_case (e.g., `optimization.py`, `test_strategies.py`)

## Project Structure

```
portfolio_management/
├── manage.py
├── pyproject.toml          # UV configuration
├── .env                    # Environment variables (not in git)
├── agent.md                # This file
├── config/                # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── portfolio/             # Main Django app
│   ├── models/            # Domain models package
│   │   ├── __init__.py
│   │   ├── assets.py
│   │   ├── accounts.py
│   │   ├── securities.py
│   │   ├── strategies.py
│   │   └── portfolio.py
│   ├── admin.py           # Admin customizations (minimal)
│   ├── views.py           # Web views
│   ├── urls.py
│   ├── services/          # Business logic layer
│   │   ├── optimization.py    # CVXPY asset location
│   │   └── rebalancing.py     # Rebalancing calculations
│   ├── templates/portfolio/   # HTML templates
│   └── tests/             # Test suite
│       ├── models/
│       ├── views/
│       ├── services/
│       └── e2e/
└── static/                # CSS, JS (minimal)
```

## Data Models

### Core Models (models/)
1. **AssetClass** - Investment categories (US Stocks, Bonds, etc.)
   - name, category, target_allocation_pct, expected_return, risk_volatility
   
2. **Security** - Individual investments (ETFs, mutual funds)
   - ticker, name, security_type, asset_class (FK), expense_ratio, tax_efficiency
   
3. **Account** - Investment accounts (IRA, 401k, Taxable)
   - name, account_type, institution, tax_treatment
   
4. **Holding** - Current positions
   - account (FK), security (FK), shares, cost_basis, as_of_date, current_price
   
5. **TargetAllocationByAccount** - Tax-optimized allocations
   - account (FK), asset_class (FK), target_allocation_pct
   
6. **RebalancingRecommendation** - Trade recommendations
   - account (FK), security (FK), action, shares, estimated_amount, reason

### Model Best Practices
- Use DecimalField for all money/percentage values (never FloatField)
- Add `created_at` and `updated_at` timestamps where relevant
- Use verbose_name and help_text for admin clarity
- Implement `__str__()` methods for readable admin display
- Add Meta class with ordering and verbose_name_plural

## Business Logic (services/)

### optimization.py - Asset Location Optimizer
**Purpose:** Determine optimal asset class allocation per account to maximize after-tax returns

**Key Functions:**
- `optimize_asset_location(accounts, target_allocation)` - Main optimization
- Uses CVXPY for convex optimization
- Constraints: account restrictions, overall target allocation, tax efficiency
- Returns: Dictionary of optimal allocations by account and asset class

**CVXPY Pattern:**
```python
import cvxpy as cp

# Define variables
allocations = cp.Variable((n_accounts, n_asset_classes))

# Define objective (maximize after-tax returns)
objective = cp.Maximize(tax_adjusted_returns)

# Define constraints
constraints = [
    cp.sum(allocations, axis=1) == account_values,  # Each account fully invested
    cp.sum(allocations, axis=0) == target_total,    # Hit target allocation
    allocations >= 0,                                # No shorts
]

# Solve
problem = cp.Problem(objective, constraints)
problem.solve()
```

### rebalancing.py - Rebalancing Calculator
**Purpose:** Generate buy/sell recommendations to restore target allocations

**Key Functions:**
- `calculate_rebalancing(account, threshold=0.05)` - Calculate trades needed
- `get_portfolio_variance(holdings, targets)` - Measure deviation from target
- Returns: List of Trade objects with security, action, shares, amount

**Algorithm:**
1. Calculate current allocation per account
2. Compare to target allocation
3. Identify securities to buy/sell
4. Minimize transaction count
5. Consider tax implications (basic wash sale awareness)

## Django Admin

### Admin Configuration (admin.py)
- **Start with defaults** - Zero customizations initially
- Register all models with `admin.site.register(Model)`
- Add customizations ONLY when pain points emerge

### Future Admin Customizations (defer these):
```python
@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'name', 'asset_class', 'security_type']
    list_filter = ['asset_class', 'security_type']
    search_fields = ['ticker', 'name']
```

## Views & Templates

### View Patterns
**Dashboard View:**
- Show current portfolio value
- Display allocation vs target (HTML table)
- Link to optimization and rebalancing

**Optimization View:**
- Form to trigger optimization
- Display results as table
- Button to save to TargetAllocationByAccount

**Rebalancing View:**
- Show current variance from target
- Calculate and display recommended trades
- Export to CSV

### Template Structure
```html
{% extends "portfolio/base.html" %}

{% block content %}
<h1>Portfolio Dashboard</h1>

<table class="table">
  <thead>
    <tr>
      <th>Asset Class</th>
      <th>Target %</th>
      <th>Current %</th>
      <th>Variance</th>
    </tr>
  </thead>
  <tbody>
    {% for allocation in allocations %}
    <tr>
      <td>{{ allocation.asset_class }}</td>
      <td>{{ allocation.target_pct }}%</td>
      <td>{{ allocation.current_pct }}%</td>
      <td class="{% if allocation.variance > 5 %}text-danger{% endif %}">
        {{ allocation.variance }}%
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

## Testing Strategy

### Use Django's Built-in Testing
```python
from django.test import TestCase
from portfolio.models import AssetClass, Security, Account, Holding
from portfolio.services.optimization import optimize_asset_location

class OptimizationTestCase(TestCase):
    def setUp(self):
        # Create test data
        self.stocks = AssetClass.objects.create(
            name="US Stocks",
            target_allocation_pct=60.0
        )
        
    def test_optimization_hits_target(self):
        result = optimize_asset_location(accounts, targets)
        self.assertAlmostEqual(result['total_stocks_pct'], 60.0, places=1)
```

### Test Coverage Goals
- Models: Test validation, computed properties, constraints
- Services: Test optimization logic, rebalancing calculations (>80% coverage)
- Views: Test basic rendering, form submissions

### Running Tests & Checks
```bash
# Run tests
uv run python manage.py test

# Run type checking
uv run mypy .

# Run linting
uv run ruff check .

# Run formatting
uv run ruff format .
```

### CI/CD & Pre-commit
- **CI**: GitHub Actions workflow runs tests, linting, and type checking on every push.
- **Pre-commit**: Install hooks to catch issues locally before committing.
```bash
# Install pre-commit hooks
uv run pre-commit install
```

## Common Commands

### UV Commands
```bash
# Install dependencies
uv pip install -e ".[dev]"

# Add new dependency
uv add package-name

# Run Django commands
uv run python manage.py runserver
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py test

# Linting and formatting
uv run ruff check .
uv run ruff format .
```

### Django Management Commands
- `makemigrations` - Create migration files
- `migrate` - Apply migrations to database
- `createsuperuser` - Create admin user
- `runserver` - Start development server
- `shell` - Django Python shell
- `dbshell` - Database shell
- `test` - Run test suite

## Environment Variables (.env)
```
SECRET_KEY=<django-secret-key>
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
```

## Important Constraints & Rules

### Financial Data Handling
- **ALWAYS use DecimalField for money and percentages** - Never float
- Round percentages to 2 decimal places for display
- Validate that allocations sum to 100%
- Handle division by zero in percentage calculations

### Optimization Constraints
- Overall portfolio must match target allocation (within tolerance)
- Each account must be fully invested (sum to account value)
- No short positions (allocations >= 0)
- Respect account-specific restrictions (e.g., limited 401k fund choices)
- Tax-deferred accounts prefer bonds (lower tax drag)
- Taxable accounts prefer tax-efficient equities

### Performance Considerations
- Use `select_related()` for foreign keys
- Use `prefetch_related()` for reverse foreign keys
- Avoid N+1 queries (check with django-debug-toolbar)
- Cache expensive calculations
- CVXPY optimization should complete in <10 seconds

## Deferred Features (Don't Build Yet)

### DO NOT implement until explicitly requested:
- Transaction history model
- Historical performance tracking
- Interactive charts (Plotly/Chart.js)
- Async views or background tasks
- PostgreSQL migration
- Multi-user authentication
- API endpoints
- Mobile responsive design (beyond basic Bootstrap)

### When Asked About Deferred Features:
- Acknowledge they're planned for future phases
- Focus on core MVP functionality first
- Suggest completing optimization and rebalancing before adding

## Security & Best Practices

### Django Security
- Keep SECRET_KEY in .env, never in code
- Use Django's built-in CSRF protection
- Validate all user inputs
- Use Django ORM (prevents SQL injection)
- Keep DEBUG=False in production

### Data Validation
- Validate percentages are 0-100
- Validate monetary amounts are positive
- Check that target allocations sum to 100%
- Ensure holdings reference valid securities and accounts

## Debugging Tips

### Common Issues
1. **CVXPY solver fails** - Check constraints aren't contradictory
2. **N+1 queries** - Use select_related/prefetch_related
3. **Percentage doesn't sum to 100** - Rounding errors, use Decimal
4. **Optimization is slow** - Reduce problem size or add constraints

### Debug Tools
- django-debug-toolbar - Check SQL queries, rendering time
- Python debugger (pdb) - `import pdb; pdb.set_trace()`
- Django shell - `uv run python manage.py shell`
- Print CVXPY problem status - `problem.status`

## Code Generation Preferences

### When Generating Code:
1. **Start minimal** - Simplest implementation that works
2. **Add comments** - Explain financial logic and constraints
3. **Use type hints** - Modern Python 3.12+ style
4. **Write tests** - At least for optimization and rebalancing
5. **Follow Django conventions** - Don't reinvent Django patterns
6. **Leverage Django admin** - Don't build custom CRUD UIs yet

### When Modifying Existing Code:
1. **Maintain consistency** - Match existing style
2. **Update tests** - When changing logic
3. **Check migrations** - After model changes
4. **Validate optimization** - Test with real scenarios

## Example Code Snippets

### Model with Best Practices
```python
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class AssetClass(models.Model):
    """Investment asset class (e.g., US Stocks, Bonds)."""
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Asset class name (e.g., 'US Large Cap Stocks')"
    )
    target_allocation_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Target allocation percentage (0-100)"
    )
    expected_return = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Expected annual return (%)"
    )
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = "Asset Classes"
    
    def __str__(self):
        return f"{self.name} ({self.target_allocation_pct}%)"
```

### Service Function Pattern
```python
from decimal import Decimal
import pandas as pd
import cvxpy as cp
from portfolio.models import Account, AssetClass

def optimize_asset_location(
    accounts: list[Account],
    asset_classes: list[AssetClass]
) -> dict[str, dict[str, Decimal]]:
    """
    Optimize asset location across accounts to maximize after-tax returns.
    
    Args:
        accounts: List of Account objects
        asset_classes: List of AssetClass objects
        
    Returns:
        Dictionary mapping account names to asset class allocations
        Example: {'Roth IRA': {'Stocks': Decimal('60.0'), 'Bonds': Decimal('40.0')}}
    """
    # Implementation using CVXPY
    n_accounts = len(accounts)
    n_classes = len(asset_classes)
    
    # Define optimization variables
    allocations = cp.Variable((n_accounts, n_classes))
    
    # Define objective and constraints
    # ... CVXPY optimization code ...
    
    # Solve and return results
    problem = cp.Problem(objective, constraints)
    problem.solve()
    
    if problem.status != cp.OPTIMAL:
        raise ValueError(f"Optimization failed with status: {problem.status}")
    
    # Format results as dictionary
    results = {}
    for i, account in enumerate(accounts):
        results[account.name] = {
            asset_classes[j].name: Decimal(str(allocations.value[i, j]))
            for j in range(n_classes)
        }
    
    return results
```

### View Pattern
```python
from django.shortcuts import render
from django.contrib import messages
from portfolio.models import Account, AssetClass
from portfolio.services.optimization import optimize_asset_location

def optimize_view(request):
    """Display and run asset location optimization."""
    
    if request.method == 'POST':
        try:
            accounts = Account.objects.all()
            asset_classes = AssetClass.objects.all()
            
            results = optimize_asset_location(accounts, asset_classes)
            
            messages.success(request, "Optimization completed successfully!")
            return render(request, 'portfolio/optimization_results.html', {
                'results': results
            })
            
        except Exception as e:
            messages.error(request, f"Optimization failed: {str(e)}")
    
    return render(request, 'portfolio/optimization_form.html')
```

## Questions to Ask Before Building

When uncertain about implementation:
1. "Does this align with the MVP scope?" (check deferred features)
2. "Can Django's built-in functionality handle this?" (prefer Django defaults)
3. "Is this optimization premature?" (start simple)
4. "Will this need tests?" (yes for business logic)
5. "Should this be in services/ or views?" (complex logic → services)

## Success Criteria

The MVP is successful when:
- Can enter data via Django admin
- Optimization runs and suggests allocations
- Rebalancing calculates trades
- All displayed in HTML tables
- Test coverage >80% for services/
- Setup from scratch takes <2 hours

## Remember

- **Keep it simple** - Resist adding features not in the plan
- **Django defaults** - Use built-in features before custom code
- **Tables first** - Charts can wait
- **Test the math** - Financial calculations must be correct
- **Document assumptions** - Tax optimization has many edge cases

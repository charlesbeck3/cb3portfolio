"""
Portfolio Test Suite Organization

Mirroring production structure with 1:1 mapping between code and tests.

## Test Categories

### Models (portfolio/models/ -> portfolio/tests/models/)
- test_accounts.py: Account model and queries
- test_assets.py: Asset class and category models
- test_portfolio.py: Portfolio model and DataFrame conversion
- test_securities.py: Security, Holding, and Price models
- test_strategies.py: AllocationStrategy and TargetAllocation models

### Domain (portfolio/domain/ -> portfolio/tests/domain/)
- test_portfolio.py: Domain aggregate root logic
- test_allocation.py: AssetAllocation value object
- test_analysis.py: Portfolio analysis calculations

### Services (portfolio/services/ -> portfolio/tests/services/)
- test_allocation_calculations.py: Core engine logic (pandas)
- test_allocation_presentation.py: Presentation formatting
- test_pricing.py: Security price resolution
- test_market_data.py: External data integration

### Views (portfolio/views/ -> portfolio/tests/views/)
- test_targets.py: Target allocation view and logic
- test_strategies.py: Allocation strategy management
- test_dashboard.py: Main dashboard view
- test_mixins.py: Shared view functionality

### Forms (portfolio/forms/ -> portfolio/tests/forms/)
- test_allocations.py: Allocation management forms
- test_strategies.py: Strategy creation forms

### Template Tags (portfolio/templatetags/ -> portfolio/tests/templatetags/)
- test_portfolio_tags.py: Formatting filters (currency, etc)
- test_allocation_tags.py: Allocation-specific display logic
- test_portfolio_filters.py: Accounting-style filters

### End-to-End Tests (portfolio/tests/e2e/)
- test_smoke_pages.py: Basic page loading
- test_target_allocations_page.py: Allocation feature flows
- test_portfolio_explicit_target.py: Complex scenarios

## Fixtures & Helpers

### Pytest Fixtures (conftest.py)
- base_system_data: Fundamental lookup data (AccountTypes, AssetClasses, etc)
- test_user: Standard test user
- test_portfolio: Pre-configured portfolio for unit testing

### Golden Reference (fixtures/golden_reference.py)
- golden_reference_portfolio: Complete real-world scenario for accuracy testing
- Used in calculations/test_golden_reference.py

## Running Tests

# All tests
uv run pytest

# Specific directory
uv run pytest portfolio/tests/views/

# With coverage
uv run pytest --cov=portfolio --cov-report=html
"""

"""
Portfolio Test Suite Organization

## Test Categories

### Unit Tests (No Database)
- test_allocation_refactored.py: Pure pandas calculation logic
  * TestPureCalculations: Zero Django dependencies
  * Uses SimpleTestCase for speed

### Integration Tests (Database Required)
- test_models.py: Model validation and database operations
- test_views.py: View logic with database fixtures
- test_allocation_vectorized.py: Calculation engine with DB data
- test_domain/: Domain logic tests with DB fixtures

### End-to-End Tests (Browser + Database)
- test_e2e/test_smoke_pages.py: Basic page loading
- test_e2e/test_dashboard_page.py: Dashboard interactions
- test_e2e/test_target_allocations_page.py: Allocation feature flows
- test_e2e/test_portfolio_explicit_target.py: Complex scenarios

### Golden Reference Tests
- test_calculations/test_golden_reference.py: Real-world portfolio scenarios
  * Hand-calculated expected values from Excel
  * Comprehensive coverage of calculation accuracy

## Fixtures & Helpers

### Base Classes
- base.PortfolioTestMixin: Shared setup for portfolio data
  * setup_portfolio_data(): Seeds system data
  * create_portfolio(): Creates user portfolio

### Pytest Fixtures (conftest.py)
- Root conftest.py: Django async configuration
- test_e2e/conftest.py: Browser testing fixtures

## Running Tests

# All tests
uv run pytest

# Specific category
uv run pytest portfolio/tests/test_e2e/
uv run pytest portfolio/tests/test_domain/

# Specific test
uv run pytest portfolio/tests/test_models.py::AccountTests::test_to_dataframe

# With coverage
uv run pytest --cov=portfolio --cov-report=html
"""

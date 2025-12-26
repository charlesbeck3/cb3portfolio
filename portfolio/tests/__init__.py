"""
Portfolio Test Suite Organization

## Test Categories

### Unit Tests (No Database)
- services/test_allocations.py: Pure pandas calculation logic
  * TestPureCalculations: Zero Django dependencies
  * Uses SimpleTestCase for speed

### Integration Tests (Database Required)
- models/: Model validation and database operations
- views/: View logic with database fixtures
- services/: Service layer tests (business logic)
- integration/: Cross-component integration tests
- calculations/: Specialized financial calculation tests

### End-to-End Tests (Browser + Database)
- e2e/test_smoke_pages.py: Basic page loading
- e2e/test_dashboard_page.py: Dashboard interactions
- e2e/test_target_allocations_page.py: Allocation feature flows
- e2e/test_portfolio_explicit_target.py: Complex scenarios

### Golden Reference Tests
- calculations/test_golden_reference.py: Real-world portfolio scenarios
  * Hand-calculated expected values from Excel
  * Comprehensive coverage of calculation accuracy

## Fixtures & Helpers

### Base Classes
- base.PortfolioTestMixin: Shared setup for portfolio data
  * setup_portfolio_data(): Seeds system data
  * create_portfolio(): Creates user portfolio

### Pytest Fixtures (conftest.py)
- Root conftest.py: Django async configuration
- e2e/conftest.py: Browser testing fixtures

## Running Tests

# All tests
uv run pytest

# Specific category
uv run pytest portfolio/tests/e2e/
uv run pytest portfolio/tests/domain/

# Specific test
uv run pytest portfolio/tests/models/test_accounts.py::TestAccount::test_to_dataframe

# With coverage
uv run pytest --cov=portfolio --cov-report=html
"""

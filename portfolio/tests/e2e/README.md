# E2E Display Validation Tests

## Quick Start

```bash
# Run all critical display tests
pytest -m "e2e and display" -v

# Run golden reference tests only
pytest -m "e2e and golden" -v

# Run specific test class
pytest portfolio/tests/e2e/test_golden_reference_display.py -v
```

## Test Categories

### Critical (Run on Every Commit)
- `test_no_invalid_values_*`: Catches NaN/undefined
- `test_all_money_values_formatted_*`: Catches missing $
- `test_all_percentages_formatted_*`: Catches missing %

### Golden Reference (Run Before Release)
- Tests with exact, known portfolio values
- Verifies mathematical accuracy end-to-end
- Catches calculation regressions

### Important (Run Before PR)
- `test_variance_color_coding_*`: Catches missing CSS classes
- `test_zero_holdings_*`: Catches division by zero

## Golden Reference Tests

Golden reference tests use portfolios with exact, pre-calculated values to verify
the complete pipeline produces mathematically correct results.

### Simple Portfolio Test
- Total: $80,000
- US Equities: $50,000 (62.5%)
- Treasuries: $30,000 (37.5%)
- Target: 60/40
- Expected variance: US +2.5%, Treasuries -2.5%

### Multi-Account Test
- Total: $100,000 across 2 accounts
- Tests aggregation across account types
- Tests large variance scenarios (+20%/-20%)

### Why Golden Reference Tests Matter
For financial applications, calculation errors can result in material losses.
Golden reference tests ensure:
1. Database -> Engine -> Template -> Display pipeline is accurate
2. Rounding errors don't accumulate
3. Aggregation logic works correctly
4. Variance calculations are mathematically correct

### Adding New Golden Reference Tests
1. Create portfolio with exact known values
2. Calculate expected results manually
3. Document the calculation in fixture docstring
4. Test each expected value with tight tolerance (<0.01)
5. Use descriptive assertion messages showing expected vs actual

## What These Tests Catch

- NaN values appearing in tables
- undefined/null showing in templates
- Missing $ or % symbols
- Wrong number formatting (50000 instead of $50,000)
- Missing variance colors (red/green indicators)
- Division by zero errors
- Calculation errors (golden reference tests)
- Rounding errors accumulating
- Aggregation bugs in multi-account scenarios

## Debugging Failed Tests

### Golden reference test fails with "got X, expected Y"
1. Check if engine calculation changed
2. Verify prices are set correctly in fixture
3. Check for rounding in formatter
4. Verify template filters not changing values
5. Manually calculate expected value to confirm

### Test fails with "NaN found on page"
1. Run with `--headed` to see the page
2. Check browser console for JavaScript errors
3. Check if calculations are returning None/null
4. Verify SecurityPrice exists for all holdings

### Test fails with "Invalid money format"
1. Check template is using `|money` filter
2. Verify formatter returns float, not string
3. Check for accidental string formatting in Python

## Test Markers

| Marker | Description | When to Run |
|--------|-------------|-------------|
| `e2e` | All end-to-end tests | CI pipeline |
| `display` | Display validation tests | Every commit |
| `golden` | Golden reference tests | Before release |
| `edge_case` | Edge case tests | Before PR |
| `journey` | User journey tests | Before release |

## Running Tests

```bash
# All E2E tests
pytest -m e2e -v

# Display tests only
pytest -m "e2e and display" -v

# Golden reference only
pytest -m "e2e and golden" -v

# Edge cases only
pytest -m "e2e and edge_case" -v

# With browser visible (debugging)
pytest -m "e2e and golden" -v --headed

# Single test
pytest portfolio/tests/e2e/test_golden_reference_display.py::TestGoldenReferenceDisplay::test_dashboard_us_equities_exact_value -vv
```

# Golden Reference Tests

## Purpose

Golden reference tests use known inputs and verified outputs to ensure the accuracy of financial calculations. These tests are critical for:

- **Accuracy**: Verifying that calculations match verified Excel/manual calculations.
- **Regression Prevention**: Ensuring that refactoring or new features don't inadvertently change calculation results.
- **Complex Scenarios**: Validating behavior across complex real-world portfolio structures.

## Standards

1. **Real Data**: Use realistic portfolio values and structures (e.g., mix of account types, tax treatments, multiple holdings).
2. **Verified Outputs**: The expected results (the "golden" standard) must be verified manually or against a trusted external source (e.g., Excel model).
3. **Tolerance**: Use appropriate tolerances for floating-point comparisons (e.g., `Decimal` precision matching).
4. **Immutability**: The golden reference data (fixtures) should not change unless the business logic or calculation methodology explicitly changes.

## Structure

- **Fixtures**: Defined in `portfolio/tests/fixtures/golden_reference.py`
  - `golden_reference_portfolio`: A comprehensive portfolio with Taxable, Traditional IRA, and Roth IRA accounts, realistic holdings, and strategy assignments.
- **Test Files**: `portfolio/tests/test_calculations/test_golden_reference.py`
- **Verification Script**: `manage.py check_golden_reference` (prints current calculation vs golden values)

## How to Add New Scenarios

1. Define the scenario in `portfolio/tests/fixtures/golden_reference.py` or a new JSON file in this directory.
2. Calculate the expected outputs manually/externally.
3. Add a test case in `portfolio/tests/test_calculations/test_golden_reference.py` asserting the output matches your verified expectations.
4. Document the scenario and source of truth here.

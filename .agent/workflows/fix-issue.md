---
description: Systematically diagnose and fix issues with step-by-step guidance.
---

# Fix Issue

When user types `/fix-issue` or describes a bug/problem:

This workflow helps systematically diagnose and fix issues.

## Step 1: Understand the Issue

Ask clarifying questions:
1. What is the expected behavior?
2. What is the actual behavior?
3. How can this be reproduced?
4. Are there any error messages?
5. Which files/components are involved?

## Step 2: Reproduce the Issue

Try to reproduce the issue:

// turbo

```bash
# If it's a test failure
pytest tests/test_[relevant].py -v

# If it's a runtime issue
python manage.py runserver
# Navigate to the problematic area

# If it's a calculation issue
python manage.py shell_plus
# Try to reproduce the calculation
```

Document the reproduction steps.

## Step 3: Identify Root Cause

### Check Common Issues

**Django Models/Database:**
- [ ] Missing migration?
  ```bash
  python manage.py makemigrations --dry-run
  ```
- [ ] N+1 queries?
  ```python
  from django.db import connection
  print(len(connection.queries))
  ```
- [ ] Validation failing?
  ```python
  obj.full_clean()  # Check what fails
  ```

**Calculations (Engines):**
- [ ] Wrong data type? (Decimal vs float)
- [ ] Missing data in DataFrame?
- [ ] Incorrect aggregation?
- [ ] Division by zero?

**Views:**
- [ ] Missing context data?
- [ ] Incorrect redirect?
- [ ] Missing permission check?

**Templates:**
- [ ] Variable not in context?
- [ ] Template inheritance issue?
- [ ] Missing template tag load?

**Type Errors:**
// turbo
```bash
mypy path/to/file.py
```

**Linting Issues:**
```bash
ruff check path/to/file.py
```

### Analyze Error Messages

If there's an error message:
1. Read the full stack trace
2. Identify the exact line causing the error
3. Understand what the error means
4. Check related code

### Check Recent Changes

```bash
# See recent commits
git log --oneline -10

# Check what changed in specific file
git log -p path/to/file.py

# See current changes
git diff
```

## Step 4: Develop Fix

### Write Failing Test First

```python
def test_[issue_description]():
    """
    Test that reproduces the reported issue.

    Issue: [Brief description]
    Expected: [Expected behavior]
    Actual: [Current behavior]
    """
    # Setup
    data = create_test_data()

    # Execute
    result = function_under_test(data)

    # Assert expected behavior
    assert result == expected_value  # This should fail now
```

Run test to confirm it fails:
```bash
pytest tests/test_fix.py::test_[issue] -v
```

### Implement Fix

Based on root cause, implement the fix following architectural patterns.

**If Domain Model Issue:**
```python
# Fix validation or business logic
def clean(self):
    # Corrected validation logic
    pass
```

**If Engine Issue:**
```python
# Fix calculation
df['result'] = df['col1'].fillna(0) * df['col2']  # Handle NaN
```

**If Formatter Issue:**
```python
# Fix formatting
def _format_currency(self, value: Decimal | None) -> str:
    if value is None:
        return "$0.00"
    return f"${value:,.2f}"
```

**If View Issue:**
```python
# Fix view logic
@login_required
def view_func(request, pk):
    obj = get_object_or_404(Model, pk=pk)  # Add safety
    # ... rest of view
```

### Verify Fix

Run the failing test again:
```bash
pytest tests/test_fix.py::test_[issue] -v
```

Should pass now.

## Step 5: Check for Side Effects

### Run Full Test Suite

```bash
# Run all tests to ensure no regressions
pytest

# Check coverage didn't decrease
pytest --cov
```

### Check Related Functionality

If you fixed a calculation engine:
- [ ] Test other calculations that use similar logic
- [ ] Check formatters that use this engine
- [ ] Test views that call this engine

If you fixed a model:
- [ ] Test all model methods
- [ ] Check migrations
- [ ] Test related models

### Manual Testing

Test the actual feature in the browser:
1. Navigate to the affected page
2. Verify the fix works
3. Test edge cases
4. Check that nothing else broke

## Step 6: Code Quality Checks

```bash
# Type check
mypy .

# Lint
ruff check .

# Format
ruff format .
```

All must pass.

## Step 7: Document the Fix

### Update Test Documentation

Add clear documentation to the test:

```python
def test_allocation_handles_zero_target():
    """
    Test that drift calculation handles zero target values gracefully.

    Bug Fix: Previously raised ZeroDivisionError when target was 0.
    Fix: Added check to return None for zero targets.

    Related: Issue #123
    """
    strategy = create_strategy_with_zero_target()
    result = strategy.calculate_drift()
    assert result is not None
```

### Update Code Comments

If the bug was subtle:

```python
def calculate_drift(self, current: Decimal, target: Decimal) -> Decimal:
    """Calculate drift."""
    # Handle zero target to avoid division by zero (Issue #123)
    if target == 0:
        return None

    return (current - target) / target
```

### Update Changelog (if significant)

If maintaining a CHANGELOG.md:

```markdown
## [Unreleased]

### Fixed
- Fixed ZeroDivisionError in drift calculation when target allocation is zero (#123)
```

## Step 8: Commit the Fix

```bash
# Stage changes
git add -A

# Commit with descriptive message
git commit -m "fix: Handle zero target values in drift calculation

Previously, calculate_drift() would raise ZeroDivisionError when
the target allocation was set to zero. Now returns None for zero
targets, which is handled gracefully by formatters.

- Added test case for zero target scenario
- Updated calculate_drift() with zero check
- Updated formatter to display 'N/A' for None values

Fixes #123"
```

## Step 9: Verify in Production-Like Environment

If possible:

```bash
# Run with production settings
DJANGO_SETTINGS_MODULE=cb3portfolio.settings.production python manage.py check --deploy

# Test with production-like data
python manage.py shell_plus
# Load production data snapshot and test
```

## Success Criteria

- ✅ Issue reproduced and understood
- ✅ Root cause identified
- ✅ Failing test written
- ✅ Fix implemented
- ✅ Test now passes
- ✅ No test regressions
- ✅ Manual testing completed
- ✅ Code quality checks pass
- ✅ Fix documented
- ✅ Changes committed

## Common Issue Patterns

### Pattern: "Object has no attribute"
**Cause:** Likely None value or wrong object type
**Fix:** Add None checks, verify object type

```python
# Before
result = obj.calculate()

# After
result = obj.calculate() if obj is not None else None
```

### Pattern: "Division by zero"
**Cause:** Missing zero check in calculations
**Fix:** Add guard clause

```python
# Before
pct = value / total

# After
pct = value / total if total != 0 else Decimal('0')
```

### Pattern: "N+1 query"
**Cause:** Missing select_related/prefetch_related
**Fix:** Optimize query

```python
# Before
items = Model.objects.all()

# After
items = Model.objects.select_related('relation').prefetch_related('many_relation')
```

### Pattern: "Template variable doesn't exist"
**Cause:** Not passed in context
**Fix:** Add to view context

```python
# Before
return render(request, 'template.html', {'item': item})

# After
return render(request, 'template.html', {
    'item': item,
    'missing_var': value,  # Add missing variable
})
```

### Pattern: "Migration conflicts"
**Cause:** Multiple branches created migrations
**Fix:** Merge migrations

```bash
python manage.py makemigrations --merge
python manage.py migrate
```

## Prevention Tips

To prevent similar issues:
1. **Write tests first** - Catches issues early
2. **Use type hints** - Catches type errors
3. **Run quality checks** - Before committing
4. **Code review** - Use checklist
5. **Test edge cases** - Don't just test happy path
6. **Monitor logs** - In production

## Get Help

If stuck:
1. Check Django documentation
2. Check pandas documentation
3. Review similar code in codebase
4. Check test fixtures for examples
5. Ask for clarification from user

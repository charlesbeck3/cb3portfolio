---
description: Run the full test suite, type checking, and code quality checks.
---

# Run Test Suite
// turbo-all

Execute the following commands in sequence and report comprehensive results.

## Commands to Run

```bash
# 1. Run full test suite with coverage
pytest --cov --cov-report=term-missing

# 2. Type checking
mypy .

# 3. Code quality checks
ruff check .
ruff format . --check
```

## Report Format

After running all commands, provide a summary in this format:

### Test Results
- **Tests Passed:** X / Y
- **Coverage:** XX.X%
- **Status:** ✅ PASS / ❌ FAIL

### Type Checking
- **Errors Found:** X
- **Status:** ✅ PASS / ❌ FAIL

### Code Quality
- **Linting Issues:** X
- **Formatting Issues:** X
- **Status:** ✅ PASS / ❌ FAIL

### Overall Status
**Ready to Commit:** ✅ YES / ❌ NO

## If Any Checks Fail

If any checks fail, provide:
1. Summary of issues
2. Suggested fixes
3. Commands to fix automatically (if applicable)

Example:
```
Formatting issues found. Run this to fix:
ruff format .
```

## Success Criteria

All checks must pass:
- ✅ All tests pass
- ✅ Coverage ≥ 90%
- ✅ No type errors
- ✅ No linting errors
- ✅ Code properly formatted

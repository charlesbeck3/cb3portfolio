---
description: Create a new calculation engine and corresponding formatter with tests.
---

# Create Calculation Engine

When user types `/create-engine [name]`:

## Step 1: Review Existing Patterns

Look at existing engines in `engines/` directory to understand patterns:
- How they inherit from `BaseEngine`
- How they use pandas DataFrames
- How they structure calculations

## Step 2: Create Engine File

Create new file: `engines/[name]_engine.py`
// turbo
```bash
touch engines/[name]_engine.py
```

Use this template:

```python
"""
[Name] calculation engine.

This engine calculates [brief description of what it calculates].
"""

import pandas as pd
from decimal import Decimal
from typing import Protocol

from .base import BaseEngine


class [Name]Engine(BaseEngine):
    """
    Engine for calculating [description].

    This engine uses pandas vectorized operations to efficiently calculate
    [what it calculates] across the entire portfolio.

    Example:
        >>> engine = [Name]Engine()
        >>> result = engine.calculate(portfolio)
        >>> print(result.head())
    """

    def calculate(self, input_data) -> pd.DataFrame:
        """
        Calculate [what this calculates].

        Args:
            input_data: Domain model or data source

        Returns:
            DataFrame with columns:
            - [column1]: [description]
            - [column2]: [description]
            - [column3]: [description]

        Example:
            >>> result = engine.calculate(portfolio)
            >>> result.columns
            Index(['column1', 'column2', 'column3'])
        """
        # Build DataFrame from input
        df = self._build_dataframe(input_data)

        # Perform vectorized calculations (NO manual loops!)
        df['result_column'] = df['input_col1'] * df['input_col2']

        # Aggregate if needed
        if self._needs_aggregation(df):
            df = self._aggregate_results(df)

        return df

    def _build_dataframe(self, input_data) -> pd.DataFrame:
        """
        Convert input data to pandas DataFrame.

        Args:
            input_data: Domain model or other data source

        Returns:
            DataFrame ready for calculations
        """
        # If input is Django queryset
        if hasattr(input_data, 'values'):
            data = input_data.values(
                'field1',
                'field2',
                'field3'
            )
            return pd.DataFrame(list(data))

        # If input is already a DataFrame
        if isinstance(input_data, pd.DataFrame):
            return input_data.copy()

        # Handle other input types
        raise TypeError(f"Unsupported input type: {type(input_data)}")

    def _needs_aggregation(self, df: pd.DataFrame) -> bool:
        """Check if results need aggregation."""
        # Implement logic to determine if aggregation needed
        return False

    def _aggregate_results(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate results using groupby.

        Use MultiIndex for hierarchical aggregations.
        """
        return df.groupby(['group_col1', 'group_col2']).agg({
            'value_col': 'sum',
            'count_col': 'count'
        })
```

## Step 3: Create Corresponding Formatter

Create file: `formatters/[name]_formatter.py`
// turbo
```bash
touch formatters/[name]_formatter.py
```

```python
"""
[Name] formatter for presentation layer.
"""

import pandas as pd
from decimal import Decimal
from typing import Any


class [Name]Formatter:
    """
    Format [Name]Engine output for display.

    This formatter converts raw calculation results into
    template-ready display format.
    """

    def format_for_display(self, engine_result: pd.DataFrame) -> dict[str, Any]:
        """
        Format engine results for template rendering.

        Args:
            engine_result: Raw DataFrame from engine

        Returns:
            Dict with formatted data ready for templates
        """
        formatted = {
            'summary': self._format_summary(engine_result),
            'details': self._format_details(engine_result),
            'total': self._format_currency(engine_result['value'].sum()),
        }
        return formatted

    def _format_summary(self, df: pd.DataFrame) -> dict:
        """Create summary statistics."""
        return {
            'count': len(df),
            'total': self._format_currency(df['value'].sum()),
            'average': self._format_currency(df['value'].mean()),
        }

    def _format_details(self, df: pd.DataFrame) -> list[dict]:
        """Convert DataFrame to list of dicts for iteration in templates."""
        details = []
        for idx, row in df.iterrows():
            details.append({
                'key': str(idx),
                'value': self._format_currency(row['value']),
                'percentage': self._format_percentage(row['pct']),
            })
        return details

    def _format_currency(self, value: Decimal) -> str:
        """Format Decimal as currency string."""
        return f"${value:,.2f}"

    def _format_percentage(self, value: float) -> str:
        """Format float as percentage string."""
        return f"{value:.2%}"
```

## Step 4: Write Comprehensive Tests

Create file: `tests/test_[name]_engine.py`
// turbo
```bash
touch tests/test_[name]_engine.py
```

```python
"""
Tests for [Name]Engine.
"""

import pytest
import pandas as pd
from decimal import Decimal

from cb3portfolio.engines.[name]_engine import [Name]Engine
from cb3portfolio.formatters.[name]_formatter import [Name]Formatter


@pytest.fixture
def sample_data(db):
    """Create sample data for testing."""
    # Setup test data
    pass


class Test[Name]Engine:
    """Test suite for [Name]Engine."""

    def test_calculate_basic(self, sample_data):
        """Test basic calculation."""
        engine = [Name]Engine()
        result = engine.calculate(sample_data)

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert 'result_column' in result.columns

    def test_calculate_empty_input(self):
        """Test with empty input."""
        engine = [Name]Engine()
        result = engine.calculate(pd.DataFrame())

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_calculate_edge_case(self, sample_data):
        """Test edge case handling."""
        # Test specific edge case
        pass

    def test_golden_reference(self, db):
        """
        Golden reference test with real data.

        CRITICAL: This test validates calculations against
        known good results from real portfolio data.
        """
        # Create real-world scenario
        real_data = create_real_scenario()

        # Calculate
        engine = [Name]Engine()
        result = engine.calculate(real_data)

        # Load golden reference
        expected = pd.read_json('tests/fixtures/golden/[name]_calculation.json')

        # Compare with tolerance
        pd.testing.assert_frame_equal(
            result,
            expected,
            rtol=0.01,  # 1% relative tolerance
            atol=0.01   # 1% absolute tolerance
        )


class Test[Name]Formatter:
    """Test suite for [Name]Formatter."""

    def test_format_for_display(self):
        """Test basic formatting."""
        # Create sample engine output
        data = pd.DataFrame({
            'value': [Decimal('1000.00'), Decimal('2000.00')],
            'pct': [0.4, 0.6]
        })

        formatter = [Name]Formatter()
        result = formatter.format_for_display(data)

        assert 'summary' in result
        assert 'details' in result
        assert 'total' in result
        assert result['total'] == '$3,000.00'


def create_real_scenario():
    """Create real-world test scenario."""
    # Use actual portfolio data for golden reference test
    pass
```

## Step 5: Run Quality Checks

Execute:

```bash
# Run new tests
pytest tests/test_[name]_engine.py -v

# Type check
mypy engines/[name]_engine.py formatters/[name]_formatter.py

# Lint
ruff check engines/[name]_engine.py formatters/[name]_formatter.py

# Format
ruff format engines/[name]_engine.py formatters/[name]_formatter.py
```

## Step 6: Integration

If this engine needs to be called from domain models:

```python
# In domain/models.py
class Portfolio(models.Model):
    # ... existing fields ...

    def calculate_[name](self) -> pd.DataFrame:
        """Calculate [description] for this portfolio."""
        from ..engines.[name]_engine import [Name]Engine
        engine = [Name]Engine()
        return engine.calculate(self)
```

## Success Criteria

Before considering this complete, verify:

- ✅ Engine file created with proper structure
- ✅ Formatter file created
- ✅ Comprehensive tests written (unit + golden reference)
- ✅ All tests pass: `pytest tests/test_[name]_engine.py`
- ✅ Type checking passes: `mypy .`
- ✅ Linting passes: `ruff check .`
- ✅ Code formatted: `ruff format .`
- ✅ Coverage >90% for new code: `pytest --cov`
- ✅ Golden reference test included with real data
- ✅ Documentation complete (docstrings)

## Key Reminders

- **Use pandas vectorization** - NO manual loops over DataFrames
- **Separate calculation from formatting** - Engine returns raw data
- **Golden reference test is mandatory** - Financial calculations require validation
- **Type hints everywhere** - No exceptions
- **Document thoroughly** - Future you will thank you

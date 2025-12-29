---
trigger: always_on
---

---
trigger: always_on
---

# Django Patterns for cb3portfolio

## Architecture: Engine → Template (UPDATED)

**CRITICAL RULE: String formatting happens ONLY in templates, never in Python.**

**NEW SIMPLIFIED FLOW:**
```
Engine → Dict structure with raw numerics (calculations + transformation)
Template → Formatted display (|money, |percent, |number)
```

**OLD FLOW (DEPRECATED):**
```
Engine → Formatter → Template  # Don't do this anymore
```

---

## Engine Pattern (UPDATED)

**Engines use pandas for calculations AND structure transformation.**

### Engine Rules
- ✅ Use pandas vectorized operations, no manual loops
- ✅ Calculate ALL numeric values (including variances)
- ✅ Return template-ready dicts with raw numeric values
- ✅ Use MultiIndex for hierarchical data
- ✅ Use Decimal for currency calculations
- ✅ Expose clean public API: `get_presentation_rows()`, `get_holdings_rows()`
- ✅ Keep formatting methods private (prefixed with `_`)
- ❌ NO separate Formatter classes
- ❌ NO string formatting (no f-strings, no `*_fmt` columns)
- ❌ NO business logic (that's in domain models)

### Engine Structure
```python
class AllocationCalculationEngine:
    """
    Calculate portfolio allocations and prepare display data.

    Public API:
    - get_presentation_rows(user) → Dashboard/targets data
    - get_holdings_rows(user, account_id) → Holdings data

    Private methods (internal use only):
    - _format_presentation_rows() → DataFrame to dicts
    - _calculate_variances() → Variance calculations
    """

    def get_presentation_rows(self, user: Any) -> list[dict[str, Any]]:
        """
        Calculate and format allocation data for display.

        Returns list of dicts with raw numeric values.
        Template handles formatting via filters.
        """
        # 1. Calculate numeric DataFrame
        df = self.build_presentation_dataframe(user=user)
        if df.empty:
            return []

        # 2. Aggregate and calculate variances
        aggregated = self.aggregate_presentation_levels(df)

        # 3. Transform to template-ready dicts
        return self._format_presentation_rows(aggregated, ...)

    def _format_presentation_rows(
        self,
        aggregated: dict[str, pd.DataFrame],
        ...
    ) -> list[dict[str, Any]]:
        """
        PRIVATE: Transform DataFrames to dicts.

        Returns raw numerics only - NO string formatting.
        """
        return [{
            'asset_class': row['name'],
            'current_value': float(row['current_value']),  # Raw!
            'current_pct': float(row['current_pct']),      # Raw!
            'variance_value': float(row['variance_value']), # Raw!
            'variance_pct': float(row['variance_pct']),    # Raw!
        } for row in data]
```

### Engine Calculation Example
```python
def aggregate_presentation_levels(self, df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Aggregate at all levels AND calculate variances.

    Returns DataFrames with ALL calculated columns ready for display.
    """
    aggregated = {
        'assets': ...,
        'subtotals': ...,
        'grand_total': ...
    }

    # Calculate variance columns for each DataFrame
    for df_name, df_data in aggregated.items():
        if not df_data.empty:
            # Portfolio variances
            df_data['portfolio_variance'] = (
                df_data['portfolio_actual'] - df_data['portfolio_effective']
            )
            df_data['portfolio_variance_pct'] = (
                df_data['portfolio_actual_pct'] - df_data['portfolio_effective_pct']
            )

            # Account variances
            for col in df_data.columns:
                if col.endswith('_actual'):
                    account_prefix = col[:-7]
                    effective_col = f"{account_prefix}_effective"
                    if effective_col in df_data.columns:
                        df_data[f"{account_prefix}_variance"] = (
                            df_data[col] - df_data[effective_col]
                        )

    return aggregated
```

### Anti-Patterns (NEVER DO THIS)
```python
# ❌ BAD - Separate Formatter class
class AllocationPresentationFormatter:
    def format_presentation_rows(self, ...):
        # Don't create separate formatter classes

# ❌ BAD - String formatting in Python
return {'value': f"${row['value']:,.0f}"}  # NO!
df['value_fmt'] = df['value'].apply(lambda x: f"${x:,.0f}")  # NO!

# ❌ BAD - Mode parameter for dollar/percent
def get_rows(self, user, mode="percent"):  # NO!

# ❌ BAD - Multi-step view orchestration
engine = Engine()
formatter = Formatter()
df = engine.build_df(user)
agg = engine.aggregate(df)
meta = engine._get_metadata(user)
rows = formatter.format(agg, meta)  # Too many steps!

# ✅ GOOD - Single clean API call
engine = AllocationCalculationEngine()
rows = engine.get_presentation_rows(user=user)  # YES!
```

---

## Template Pattern

**Templates handle ALL string formatting using custom filters.**

### Template Filters
```python
# portfolio/templatetags/portfolio_filters.py
@register.filter
def money(value):
    """$1,234 or ($1,234)"""
    val = float(value)
    formatted = f"${abs(val):,.0f}"
    return f"({formatted})" if val < 0 else formatted

@register.filter
def percent(value, decimals=1):
    """12.5% or (12.5%)"""
    val = float(value)
    formatted = f"{abs(val):.{decimals}f}%"
    return f"({formatted})" if val < 0 else formatted

@register.filter
def number(value, decimals=0):
    """1,234 or (1,234)"""
    val = float(value)
    formatted = f"{abs(val):,.{decimals}f}"
    return f"({formatted})" if val < 0 else formatted
```

### Template Usage
```django
{% load portfolio_filters %}

{# Raw numeric values from Engine, formatted by template #}
<td class="money">{{ row.current_value|money }}</td>
<td class="percent">{{ row.current_pct|percent }}</td>
<td class="money">{{ row.variance_value|money }}</td>
<td class="percent">{{ row.variance_pct|percent:2 }}</td>
```

### Template CSS
```css
.money, .percent, .number {
    display: inline-block;
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
```

---

## View Pattern (SIMPLIFIED)

**Views make single Engine call. NO business logic, NO multi-step orchestration.**

```python
from portfolio.services.allocation_calculations import AllocationCalculationEngine

@login_required
def portfolio_dashboard(request):
    """Dashboard view - single Engine call."""
    user = request.user

    # Single clean API call
    engine = AllocationCalculationEngine()
    rows = engine.get_presentation_rows(user=user)

    # Template handles money/percent formatting
    return render(request, 'portfolio/dashboard.html', {
        'allocation_rows': rows,
    })

@login_required
def holdings_view(request, account_id=None):
    """Holdings view - single Engine call."""
    user = request.user

    # Single clean API call
    engine = AllocationCalculationEngine()
    rows = engine.get_holdings_rows(user=user, account_id=account_id)

    return render(request, 'portfolio/holdings.html', {
        'holdings_rows': rows,
    })
```

### View Rules
- ✅ Single Engine method call per view
- ✅ Pass raw numeric data to templates
- ✅ Let templates handle formatting
- ❌ NO business logic or calculations
- ❌ NO multi-step orchestration (engine → formatter → ...)
- ❌ NO string formatting
- ❌ NO separate Formatter instantiation

---

## Complete Data Flow (UPDATED)

```python
# 1. Engine calculates - raw numerics
df = pd.DataFrame({
    'current_value': [50000.0],  # float, not "$50,000"
    'current_pct': [62.5],        # float, not "62.5%"
    'variance_value': [-5000.0],  # float, not "($5,000)"
    'variance_pct': [-7.5],       # float, not "(7.5%)"
})

# 2. Engine transforms to dicts - raw numerics
rows = engine.get_presentation_rows(user)
# Returns: [{'current_value': 50000.0, 'current_pct': 62.5, ...}]

# 3. View passes raw data
context = {'rows': rows}

# 4. Template formats for display
# {{ row.current_value|money }} → "$50,000"
# {{ row.current_pct|percent }} → "62.5%"
# {{ row.variance_value|money }} → "($5,000)"
# {{ row.variance_pct|percent }} → "(7.5%)"
```

---

## Testing Patterns (UPDATED)

```python
@pytest.mark.services
class TestAllocationCalculationEngine:
    """Test Engine - calculations and formatting together."""

    def test_get_presentation_rows_returns_raw_numerics(self, engine, user):
        """Verify Engine returns raw numeric values."""
        rows = engine.get_presentation_rows(user=user)

        assert isinstance(rows, list)
        row = rows[0]

        # All values should be raw numerics
        assert isinstance(row['current_value'], (int, float))
        assert isinstance(row['variance_pct'], (int, float))

        # NO formatted strings
        assert not isinstance(row['current_value'], str)

    def test_get_presentation_rows_includes_variances(self, engine, user):
        """Verify Engine calculates variance columns."""
        rows = engine.get_presentation_rows(user=user)

        row = rows[0]
        assert 'variance_value' in row
        assert 'variance_pct' in row

        # Variance should be calculated: actual - target
        assert row['variance_value'] == row['actual_value'] - row['target_value']
```

---

## Migration Checklist

When consolidating existing Engine + Formatter pattern:

- [ ] Move all calculations to Engine
- [ ] Move all DataFrame→dict transformation to private Engine methods
- [ ] Create public `get_*_rows()` methods
- [ ] Delete separate Formatter class
- [ ] Update views to use single Engine call
- [ ] Update tests to test Engine only
- [ ] Verify all numeric values remain raw (no formatting)
- [ ] Verify templates handle all formatting
- [ ] Ensure test coverage maintained

---

## Key Principles

1. **Engine does everything except string formatting**
   - Calculations (pandas)
   - Aggregations (groupby, sum)
   - Variance calculations (actual - target)
   - Structure transformation (DataFrame → dicts)

2. **Templates do all string formatting**
   - Money: `|money`
   - Percent: `|percent`
   - Numbers: `|number`

3. **Views are thin orchestration only**
   - Single Engine method call
   - Pass raw data to template
   - NO business logic

4. **No separate Formatter classes**
   - If always used with Engine, merge it
   - Formatting methods become private Engine methods
   - Public API: `get_presentation_rows()`, `get_holdings_rows()`

---
trigger: always_on
---

---
trigger: always_on
---

# Django Patterns for cb3portfolio

## Architecture: Engine → Formatter → Template

**CRITICAL RULE: String formatting happens ONLY in templates, never in Python.**

```
Engine → Raw numeric DataFrames (calculations)
Formatter → Dict structure (NO string formatting!)
Template → Formatted display (|money, |percent, |number)
```

---

## Engine Pattern

**Engines use pandas for calculations, return ONLY numeric DataFrames.**

### Engine Rules
- ✅ Use pandas vectorized operations, no manual loops
- ✅ Return raw DataFrames with ONLY numeric values
- ✅ Use MultiIndex for hierarchical data
- ✅ Use Decimal for currency calculations
- ❌ NO formatting (no f-strings, no `*_fmt` columns)
- ❌ NO business logic (that's in domain models)

### Engine Example
```python
class AllocationEngine(BaseEngine):
    def calculate_drift(self, user) -> pd.DataFrame:
        """Returns DataFrame with ONLY numeric columns."""
        data = self._build_dataframe(user)
        data['drift_value'] = data['current'] - data['target']
        data['drift_pct'] = (data['drift_value'] / data['target']).fillna(0)
        return data.groupby(['account_type', 'asset_class']).sum()
```

---

## Formatter Pattern

**Formatters transform DataFrame structure to dicts. NO STRING FORMATTING.**

### Formatter Rules
- ✅ Transform DataFrame → nested dicts (structure only)
- ✅ Return raw numeric values (float, Decimal, int)
- ✅ Include BOTH dollar and percent values
- ✅ Add boolean flags for UI logic
- ❌ NO string formatting (`f"${x:,.0f}"` is FORBIDDEN)
- ❌ NO `*_fmt` or `*_display` columns
- ❌ NO pandas `.apply()` with formatting lambdas
- ❌ NO `mode` parameter for dollar/percent switching
- ❌ NO calculations (engine's job)

### Formatter Example
```python
class AllocationFormatter:
    def format_for_display(self, df: pd.DataFrame) -> list[dict]:
        """Transform to dicts with raw numerics."""
        return [{
            'asset_class': idx[1],
            'current_value': float(row['current_value']),  # Raw!
            'current_pct': float(row['current_pct']),      # Raw!
            'drift_value': float(row['drift_value']),      # Raw!
            'drift_pct': float(row['drift_pct']),          # Raw!
        } for idx, row in df.iterrows()]
```

### Anti-Patterns (NEVER DO THIS)
```python
# ❌ BAD - Formatting in formatter
return [{'value': f"${row['value']:,.0f}"}]  # NO!
df['value_fmt'] = df['value'].apply(lambda x: f"${x:,.0f}")  # NO!
def format_rows(self, df, mode="percent"):  # NO mode parameter!

# ✅ GOOD - Raw numerics
return [{'value': float(row['value'])}]  # YES!
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
<td class="money">{{ row.current_value|money }}</td>
<td class="percent">{{ row.drift_pct|percent }}</td>
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

## View Pattern

**Views orchestrate engines and formatters. NO business logic.**

```python
@login_required
def portfolio_detail(request, pk):
    user = request.user
    engine = AllocationCalculationEngine()
    df = engine.build_dataframe(user)
    formatter = AllocationPresentationFormatter()
    rows = formatter.format_rows(df)  # No mode parameter!
    return render(request, 'template.html', {'rows': rows})
```

### View Rules
- ✅ Orchestrate engines and formatters
- ✅ Pass raw numeric data to templates
- ❌ NO business logic or calculations
- ❌ NO formatting
- ❌ NO `mode="dollar"` or `mode="percent"` (old pattern)

---

## Complete Data Flow

```python
# 1. Engine - raw numerics
df = pd.DataFrame({
    'current_value': [50000.0],  # float, not "$50,000"
    'current_pct': [62.5],        # float, not "62.5%"
})

# 2. Formatter - raw numerics in dicts
rows = [{'current_value': 50000.0, 'current_pct': 62.5}]

# 3. View - pass raw data
context = {'rows': rows}

# 4. Template - apply formatting
{{ row.current_value|money }}   <!-- $50,000 -->
{{ row.current_pct|percent }}   <!-- 62.5% -->
```

---

## Database Optimization

```python
# ✅ Use select_related/prefetch_related
holdings = Holding.objects.filter(
    account__user=user
).select_related('account', 'security__asset_class')

# ❌ NO N+1 queries
holdings = Holding.objects.all()
for h in holdings:
    asset = h.security.asset_class  # Separate query!
```

---

## Testing

```python
# Test engines return numerics
assert isinstance(result.iloc[0]['value'], (float, int))
assert not isinstance(result.iloc[0]['value'], str)

# Test formatters return numerics
assert isinstance(rows[0]['value'], float)
assert '$' not in str(rows[0]['value'])

# Test filters
assert money(1234.56) == "$1,235"
assert money(-1234.56) == "($1,235)"
```

---

## Migration Checklist

**Updating existing code:**
1. Delete `_format_value()`, `_format_variance()`, `_format_money()`
2. Remove all `*_fmt` and `*_display` column creation
3. Change `f"${value:,.0f}"` to `float(value)`
4. Remove `mode` parameter from formatters
5. Update templates: `{% load portfolio_filters %}`
6. Change `{{ value }}` to `{{ value|money }}`
7. Update tests: `assert value == 1234.0` not `"$1,234"`

---

## The Three Rules

1. **Engines:** Raw numeric DataFrames (NO formatting)
2. **Formatters:** Structure transformation (DataFrame → dict, NO formatting)
3. **Templates:** Display formatting (|money, |percent, |number)

**String formatting is ALWAYS a template concern, NEVER a Python concern.**

---
trigger: always_on
---

---
trigger: always_on
---

# Django Patterns for cb3portfolio

## Composition Architecture

**Services use composition with dependency injection.**

```
portfolio/services/allocations/
├── __init__.py           # Public API
├── engine.py            # Orchestration
├── calculations.py      # Pure pandas logic
├── data_providers.py    # ORM → pandas
├── formatters.py        # DataFrame → dict
└── types.py             # TypedDict schemas
```

### Component Pattern

**Calculator (Pure Logic)**
- No Django dependencies
- Pure pandas calculations
- Returns DataFrames with numeric values

**DataProvider (ORM → Pandas)**
- All Django queries here
- Convert to pandas DataFrames
- Optimize with select_related/prefetch_related

**Formatter (DataFrame → Dict)**
- Transform structure for templates
- Return raw numeric values (no string formatting)

**Engine (Orchestration)**
- Compose components via dependency injection
- Expose clean public API
- Handle logging and errors

**Public API (__init__.py)**
- Module-level convenience functions
- Views call these, not Engine directly

## View Pattern

**Views make single API call.**

```python
from portfolio.services.allocations import get_presentation_rows

@login_required
def dashboard(request):
    rows = get_presentation_rows(user=request.user)
    return render(request, 'portfolio/dashboard.html', {'allocation_rows': rows})
```

**Rules:**
- ✅ Single module function call
- ✅ Pass raw numeric data to templates
- ❌ NO business logic or calculations
- ❌ NO component instantiation
- ❌ NO multi-step orchestration

## Template Pattern

**Templates format via filters.**

```python
# portfolio/templatetags/portfolio_filters.py
@register.filter
def money(value):
    val = float(value)
    formatted = f"${abs(val):,.0f}"
    return f"({formatted})" if val < 0 else formatted

@register.filter
def percent(value, decimals=1):
    val = float(value)
    formatted = f"{abs(val):.{decimals}f}%"
    return f"({formatted})" if val < 0 else formatted
```

```django
{% load portfolio_filters %}
<td>{{ row.portfolio.actual|money }}</td>
<td>{{ row.portfolio.actual_pct|percent }}</td>
```

## Data Flow

```
View → get_presentation_rows(user)
        → Engine.get_presentation_rows()
          → DataProvider → Calculator → Formatter
            → list[dict] with raw floats
              → Template filters format strings
```

## Testing Pattern

**Unit Test Components:**
```python
# Calculator (no Django)
def test_calculator():
    calc = AllocationCalculator()
    df = pd.DataFrame({...})
    result = calc.build_presentation_dataframe(df, ...)
    assert 'portfolio_actual' in result.columns

# DataProvider (with Django)
@pytest.mark.django_db
def test_data_provider(test_user):
    provider = DjangoDataProvider()
    df = provider.get_holdings_df(test_user)
    assert not df.empty

# Formatter (no Django)
def test_formatter():
    formatter = AllocationFormatter()
    rows = formatter.to_presentation_rows(df, ...)
    assert isinstance(rows[0]['portfolio']['actual'], float)
```

**Integration Test:**
```python
@pytest.mark.django_db
def test_integration(test_user):
    rows = get_presentation_rows(test_user)
    assert len(rows) > 0
```

**Mock Dependencies:**
```python
def test_engine_mocks():
    engine = AllocationEngine(
        calculator=Mock(),
        data_provider=Mock(),
        formatter=Mock(),
    )
    # Test orchestration logic
```

## Anti-Patterns

❌ **Multi-step view orchestration**
```python
# BAD
provider = DjangoDataProvider()
calculator = AllocationCalculator()
formatter = AllocationFormatter()
df = provider.get_holdings_df(user)
result = calculator.build(df)
rows = formatter.format(result)
```

✅ **Single API call**
```python
# GOOD
rows = get_presentation_rows(user=user)
```

❌ **String formatting in Python**
```python
return {'value': f"${amount:,.0f}"}  # NO!
```

✅ **Raw values + template filters**
```python
return {'value': float(amount)}  # YES!
```

❌ **Django in Calculator**
```python
class Calculator:
    def calc(self, user):
        holdings = Holding.objects.filter(...)  # NO!
```

✅ **Pure pandas logic**
```python
class Calculator:
    def calc(self, holdings_df: pd.DataFrame):
        return holdings_df.groupby(...)  # YES!
```

## QuerySet Optimization

```python
# Always prefetch to avoid N+1
holdings = (
    Holding.objects
    .filter(account__user=user)
    .select_related('security', 'account', 'security__asset_class')
    .prefetch_related('security__latest_price')
)
```

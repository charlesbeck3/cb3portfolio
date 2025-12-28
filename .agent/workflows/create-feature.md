---
description: Guide to creating a complete feature following architectural patterns.
---

# Create Feature

When user types `/create-feature [feature_name]`:

This workflow guides through creating a complete feature following architectural patterns.

## Phase 1: Planning

### Step 1: Understand Requirements

Ask the user:
1. What does this feature do?
2. What data does it work with?
3. Is this CRUD, calculation, or workflow?
4. What's the user interaction?

### Step 2: Identify Architectural Layers

Determine which layers are needed:

**Domain Model:**
- [ ] New model needed?
- [ ] Existing model changes?
- [ ] Business constraints to enforce?

**Engine (Calculation):**
- [ ] Financial calculations needed?
- [ ] Data aggregation required?
- [ ] Performance-critical operations?

**Formatter:**
- [ ] Display formatting needed?
- [ ] Complex data transformations?

**Service:**
- [ ] Multiple operations to coordinate?
- [ ] External integrations?
- [ ] Transaction management?

**View:**
- [ ] New endpoint needed?
- [ ] Existing view modification?

**Template:**
- [ ] New page/component?
- [ ] Existing template changes?

## Phase 2: Implementation

### Step 3: Create/Modify Domain Model

If domain model changes needed:

**File:** `domain/models.py`

```python
class [ModelName](models.Model):
    """
    Domain model for [description].

    Business rules:
    - [Rule 1]
    - [Rule 2]
    """

    # Fields
    field1 = models.CharField(max_length=100)
    field2 = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name_plural = "[model name plural]"
        indexes = [
            models.Index(fields=['field1', 'field2']),
        ]

    def __str__(self):
        return f"{self.field1}"

    def clean(self):
        """Enforce business constraints."""
        # Validation logic
        pass

    def [business_method](self) -> Any:
        """Business logic method."""
        # Delegates to engine if calculation needed
        pass
```

Create migration:
```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 4: Create Engine (If Needed)

If calculations required, use `/create-engine [name]` workflow.

Or create directly:

**File:** `engines/[feature]_engine.py`
// turbo
```bash
touch engines/[feature]_engine.py
```

```python
"""[Feature] calculation engine."""

import pandas as pd
from .base import BaseEngine


class [Feature]Engine(BaseEngine):
    """Calculate [what this calculates]."""

    def calculate(self, input_data) -> pd.DataFrame:
        """
        Main calculation method.

        Uses vectorized pandas operations for performance.
        """
        df = self._build_dataframe(input_data)

        # Vectorized calculations
        df['result'] = df['col1'] * df['col2']

        return df

    def _build_dataframe(self, input_data) -> pd.DataFrame:
        """Convert input to DataFrame."""
        # Implementation
        pass
```

### Step 5: Create Formatter (If Needed)

**File:** `formatters/[feature]_formatter.py`
// turbo
```bash
touch formatters/[feature]_formatter.py
```

```python
"""[Feature] formatter for display."""

import pandas as pd
from decimal import Decimal


class [Feature]Formatter:
    """Format [feature] data for templates."""

    def format_for_display(self, engine_result: pd.DataFrame) -> dict:
        """Convert engine output to template-ready format."""
        return {
            'items': self._format_items(engine_result),
            'summary': self._format_summary(engine_result),
        }

    def _format_items(self, df: pd.DataFrame) -> list[dict]:
        """Format individual items."""
        items = []
        for idx, row in df.iterrows():
            items.append({
                'name': row['name'],
                'value': f"${row['value']:,.2f}",
            })
        return items

    def _format_summary(self, df: pd.DataFrame) -> dict:
        """Format summary statistics."""
        return {
            'total': f"${df['value'].sum():,.2f}",
            'count': len(df),
        }
```

### Step 6: Create/Update Service (If Needed)

**File:** `domain/services.py`

```python
"""Domain services for orchestration."""

from django.db import transaction
import structlog

logger = structlog.get_logger(__name__)


class [Feature]Service:
    """Service for [feature] operations."""

    def __init__(self):
        # Initialize dependencies
        pass

    @transaction.atomic
    def execute_[operation](self, input_data) -> dict:
        """
        Execute [operation].

        This service orchestrates multiple operations.
        """
        # Orchestration logic
        logger.info(
            "[operation]_started",
            input_id=input_data.id
        )

        # Do work
        result = self._do_work(input_data)

        logger.info(
            "[operation]_completed",
            input_id=input_data.id,
            result_count=len(result)
        )

        return result
```

### Step 7: Create/Update View

**File:** `views.py` or `views/[feature]_views.py`

```python
"""Views for [feature]."""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import [Model]
from ..engines.[feature]_engine import [Feature]Engine
from ..formatters.[feature]_formatter import [Feature]Formatter


@login_required
def [feature]_list(request):
    """List all [items]."""
    items = [Model].objects.select_related('related_model').all()

    return render(request, '[feature]/list.html', {
        'items': items,
    })


@login_required
def [feature]_detail(request, pk):
    """Display [item] details."""
    item = get_object_or_404([Model], pk=pk)

    # Calculate if needed
    if needs_calculation(item):
        engine = [Feature]Engine()
        calculation_result = engine.calculate(item)

        formatter = [Feature]Formatter()
        display_data = formatter.format_for_display(calculation_result)
    else:
        display_data = None

    return render(request, '[feature]/detail.html', {
        'item': item,
        'data': display_data,
    })


@login_required
def [feature]_create(request):
    """Create new [item]."""
    if request.method == 'POST':
        form = [Feature]Form(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, f'{item} created successfully.')
            return redirect('[feature]:detail', pk=item.pk)
    else:
        form = [Feature]Form()

    return render(request, '[feature]/form.html', {
        'form': form,
        'action': 'Create',
    })
```

### Step 8: Create/Update URLs

**File:** `urls.py` or `urls/[feature]_urls.py`

```python
"""URLs for [feature]."""

from django.urls import path
from . import views

app_name = '[feature]'

urlpatterns = [
    path('', views.[feature]_list, name='list'),
    path('<int:pk>/', views.[feature]_detail, name='detail'),
    path('create/', views.[feature]_create, name='create'),
    path('<int:pk>/edit/', views.[feature]_edit, name='edit'),
    path('<int:pk>/delete/', views.[feature]_delete, name='delete'),
]
```

Include in main urls.py:
```python
urlpatterns = [
    # ...
    path('[feature]/', include('cb3portfolio.urls.[feature]_urls')),
]
```

### Step 9: Create Templates

**File:** `templates/[feature]/list.html`

```html
{% extends "base.html" %}

{% block title %}[Feature List]{% endblock %}

{% block content %}
<div class="container">
    <h1>[Feature List]</h1>

    <a href="{% url '[feature]:create' %}" class="btn btn-primary">
        Create New [Item]
    </a>

    <div class="item-list">
        {% for item in items %}
        <div class="item-card">
            <h3><a href="{% url '[feature]:detail' item.pk %}">{{ item.name }}</a></h3>
            <p>{{ item.description }}</p>
        </div>
        {% empty %}
        <p>No items found.</p>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

**File:** `templates/[feature]/detail.html`

```html
{% extends "base.html" %}

{% block title %}{{ item.name }}{% endblock %}

{% block content %}
<div class="container">
    <h1>{{ item.name }}</h1>

    {% if data %}
    <div class="calculation-results">
        <h2>Analysis</h2>
        <div class="summary">
            <p>Total: {{ data.summary.total }}</p>
            <p>Count: {{ data.summary.count }}</p>
        </div>

        <div class="details">
            {% for detail in data.items %}
            <div class="detail-item">
                <span>{{ detail.name }}:</span>
                <span>{{ detail.value }}</span>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <div class="actions">
        <a href="{% url '[feature]:edit' item.pk %}" class="btn btn-secondary">Edit</a>
        <a href="{% url '[feature]:delete' item.pk %}" class="btn btn-danger">Delete</a>
    </div>
</div>
{% endblock %}
```

## Phase 3: Testing

### Step 10: Write Comprehensive Tests

**File:** `tests/test_[feature].py`

```python
"""Tests for [feature]."""

import pytest
from decimal import Decimal
from django.urls import reverse

from cb3portfolio.models import [Model]
from cb3portfolio.engines.[feature]_engine import [Feature]Engine


@pytest.fixture
def sample_[item](db):
    """Create sample [item] for testing."""
    return [Model].objects.create(
        field1="Test",
        field2=Decimal('100.00')
    )


class Test[Model]:
    """Test [Model] domain model."""

    def test_create(self, db):
        """Test model creation."""
        item = [Model].objects.create(field1="Test")
        assert item.field1 == "Test"

    def test_business_constraint(self, sample_[item]):
        """Test business rule enforcement."""
        # Test constraint
        pass


class Test[Feature]Engine:
    """Test [Feature]Engine calculations."""

    def test_calculate(self, sample_[item]):
        """Test basic calculation."""
        engine = [Feature]Engine()
        result = engine.calculate(sample_[item])

        assert len(result) > 0

    def test_golden_reference(self, db):
        """Golden reference test with real data."""
        # Load real scenario
        # Calculate
        # Compare with golden reference
        pass


class Test[Feature]Views:
    """Test [feature] views."""

    def test_list_view(self, client, sample_[item]):
        """Test list view."""
        response = client.get(reverse('[feature]:list'))
        assert response.status_code == 200
        assert sample_[item].field1 in str(response.content)

    def test_detail_view(self, client, sample_[item]):
        """Test detail view."""
        response = client.get(reverse('[feature]:detail', args=[sample_[item].pk]))
        assert response.status_code == 200
```

### Step 11: Run All Quality Checks

```bash
# Run new tests
pytest tests/test_[feature].py -v

# Run full test suite
pytest

# Check coverage
pytest --cov

# Type check
mypy .

# Lint and format
ruff check .
ruff format .
```

## Phase 4: Documentation

### Step 12: Update README.md

Add section for new feature:

```markdown
## [Feature Name]

Brief description of what this feature does.

### Usage

```python
# Example code showing how to use
```

### Architecture

- **Domain Model:** `[Model]` - [description]
- **Engine:** `[Feature]Engine` - [what it calculates]
- **Formatter:** `[Feature]Formatter` - [how it formats]
- **Views:** [list of views]

### Testing

Run feature-specific tests:
```bash
pytest tests/test_[feature].py -v
```
```

## Success Criteria

Before considering feature complete:

- ✅ All architectural layers implemented correctly
- ✅ Domain models enforce business constraints
- ✅ Calculations use pandas (if applicable)
- ✅ Formatting separated from calculation
- ✅ Views are thin (orchestration only)
- ✅ Comprehensive tests written (>90% coverage)
- ✅ Golden reference tests for calculations
- ✅ All tests passing: `pytest`
- ✅ Type checking pas

# HTMX Implementation Plan for Dynamic Target Allocation Updates

## Overview

Replace the removed JavaScript-based dynamic calculation with HTMX to provide real-time feedback as users input target allocations. This approach keeps all calculation logic server-side in Python, leveraging existing services while providing a responsive UX.

## Goals

1. Provide instant visual feedback when users modify target allocation inputs
2. Keep calculation logic in Python (reuse existing TargetAllocationService)
3. Update displayed values: Total Portfolio Target %, Variance %, Category Subtotals, Cash Row
4. Minimal JavaScript footprint (just HTMX library)
5. Progressive enhancement (graceful degradation if JS disabled)

---

## Architecture Overview

```
User types in input → HTMX intercepts → POST to endpoint → 
Django recalculates → Returns updated table HTML → HTMX swaps content
```

**Key Components:**
- HTMX library (CDN link in base template)
- New Django endpoint: `calculate_allocations_preview` 
- Modified template with `hx-*` attributes
- Existing `TargetAllocationService` (reused for calculations)

---

## Implementation Steps

### Step 1: Add HTMX to Base Template

**File:** `portfolio/templates/base.html` (or wherever your common head section is)

**Action:** Add HTMX CDN link before closing `</body>` tag:

```html
<!-- Add before </body> -->
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
```

**Optional:** Add HTMX debug extension during development:
```html
<script src="https://unpkg.com/htmx.org@1.9.10/dist/ext/debug.js"></script>
```

---

### Step 2: Create New Calculation Preview Endpoint

**File:** `portfolio/views/target_allocations.py` (or create new `portfolio/views/targets_preview.py`)

**Action:** Create a new view that:
1. Accepts POST with all form data (all current input values)
2. Does NOT save to database
3. Calculates what the table would look like with those values
4. Returns only the table HTML (not full page)

**New View Signature:**
```python
def calculate_allocations_preview(request: HttpRequest) -> HttpResponse:
    """
    Calculate and return updated allocation table HTML without saving.
    
    Accepts: POST with all target allocation form data
    Returns: Rendered table partial (just the <table> element)
    """
```

**Logic Flow:**
```
1. Parse form data (same as existing save logic)
2. Build temporary allocation structures (DON'T save to DB)
3. Call existing services to calculate:
   - Weighted targets
   - Variances
   - Category subtotals
   - Cash implicit allocation
4. Render ONLY the table template with updated data
5. Return HttpResponse with table HTML
```

**Key Implementation Details:**
- Reuse parsing logic from existing `TargetAllocationService.save_targets()`
- Create temporary in-memory allocation maps (don't hit database)
- Use existing `_build_allocation_table_data()` or similar helper
- Return only `_allocation_table.html` partial, not full page
- Add CSRF exemption if needed (or include CSRF token in HTMX config)

---

### Step 3: Add URL Route

**File:** `portfolio/urls.py` (or `portfolio/targets/urls.py`)

**Action:** Add route for preview endpoint:

```python
from portfolio.views.target_allocations import calculate_allocations_preview

urlpatterns = [
    # ... existing patterns ...
    path(
        'targets/preview/',
        calculate_allocations_preview,
        name='targets_preview'
    ),
]
```

---

### Step 4: Update Template with HTMX Attributes

**File:** `portfolio/templates/portfolio/_allocation_table.html`

**Changes Needed:**

#### 4a. Wrap table in a form (if not already)
```html
<form id="allocation-form" hx-post="{% url 'targets_preview' %}" 
      hx-trigger="input from:.allocation-input delay:300ms"
      hx-target="#allocation-table-container"
      hx-swap="innerHTML">
    
    {% csrf_token %}
    
    <div id="allocation-table-container">
        <table class="table..." id="{{ table_id }}">
            <!-- existing table structure -->
        </table>
    </div>
</form>
```

**Explanation:**
- `hx-post`: Endpoint to call
- `hx-trigger`: Listen for input events on elements with `.allocation-input` class, debounced 300ms
- `hx-target`: Replace contents of this div
- `hx-swap`: How to swap (innerHTML replaces content inside div)

#### 4b. Add class to input elements
Both default inputs and override inputs need the trigger class:

```html
<!-- Default Input (account type level) -->
<input type="number"
       name="{{ group.account_type.target_input_name }}"
       class="form-control form-control-sm text-end default-input allocation-input px-1"
       ...>

<!-- Override Input (individual account level) -->
<input type="number"
       name="{{ acc.input_name }}"
       class="form-control form-control-sm text-end override-input allocation-input px-1"
       ...>
```

**Key:** Add `allocation-input` class to trigger HTMX on any input change.

#### 4c. Ensure IDs are present on target cells
The template already has these IDs (good!):
- `id="row-total-{{ row.asset_class_id }}"` - Portfolio Target
- `id="row-var-{{ row.asset_class_id }}"` - Portfolio Variance
- `id="sub-total-target-{{ row.category_code }}"` - Category Subtotal
- `id="cash-total"` - Cash Total Target
- `id="cash-var"` - Cash Variance

These will be automatically updated when HTMX swaps the table.

---

### Step 5: Handle CSRF Token for HTMX

**Option A: Include in form (easiest)**
Already done if you wrap in `<form>` with `{% csrf_token %}`

**Option B: Configure HTMX globally**
In base template, after HTMX script:
```html
<script>
document.body.addEventListener('htmx:configRequest', (event) => {
    event.detail.headers['X-CSRFToken'] = '{{ csrf_token }}';
});
</script>
```

---

### Step 6: Implement the Preview View Logic

**File:** `portfolio/views/target_allocations.py`

**Pseudocode:**
```python
def calculate_allocations_preview(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest()
    
    user = request.user
    
    # Parse form data into temporary structures
    # (similar to save_targets but don't commit)
    parsed_data = _parse_allocation_form_data(request.POST, user)
    
    # Calculate allocations with parsed data
    # Use existing PortfolioSummaryService or similar
    table_data = _calculate_preview_table_data(
        user=user,
        default_allocations=parsed_data['defaults'],
        override_allocations=parsed_data['overrides']
    )
    
    # Render just the table partial
    return render(
        request,
        'portfolio/_allocation_table.html',
        {
            'table_id': 'allocation-table',
            'mode': 'percent',
            'account_types': table_data['account_types'],
            'rows': table_data['rows'],
        }
    )
```

**Helper Functions Needed:**

```python
def _parse_allocation_form_data(post_data, user):
    """
    Parse POST data into allocation structures.
    Returns: {
        'defaults': {account_type_id: {asset_class_id: Decimal}},
        'overrides': {account_id: {asset_class_id: Decimal}}
    }
    """
    # Parse target_{at_id}_{ac_id} → defaults
    # Parse target_account_{acc_id}_{ac_id} → overrides
    ...

def _calculate_preview_table_data(user, default_allocations, override_allocations):
    """
    Calculate what the table should show with given allocations.
    Does NOT touch database.
    
    Returns: Structure matching template needs (account_types, rows)
    """
    # 1. Get current holdings/values (from DB, read-only)
    # 2. Apply temporary allocations (in memory)
    # 3. Calculate weighted targets, variances
    # 4. Build row/column structure for template
    ...
```

---

### Step 7: Update Tests

**File:** `portfolio/tests/test_frontend_allocations.py`

**Changes:**

#### 7a. Update test expectations
Tests should still work! HTMX automatically triggers on input events that Playwright's `.fill()` generates.

**Potential issues:**
- May need to add `page.wait_for_htmx()` or use `expect(...).to_have_text(..., timeout=5000)`
- The `live_server` fixture should handle HTMX requests

#### 7b. Add wait helper (if needed)
```python
def wait_for_htmx(page: Page):
    """Wait for HTMX request to complete."""
    page.wait_for_selector('body:not(.htmx-request)', timeout=5000)
```

#### 7c. Update test to wait for updates
```python
input_locator.fill("50")
page.wait_for_timeout(500)  # Wait for debounce + request
expect(page.locator(row_total_selector)).to_have_text("50.0%")
```

---

## Testing Plan

### Manual Testing
1. Navigate to targets page
2. Open browser DevTools Network tab
3. Type in allocation input
4. Verify:
   - POST request to `/targets/preview/` after 300ms
   - Response contains table HTML
   - Table updates in UI
   - Totals/variances recalculate correctly

### Automated Testing
1. Run existing Playwright tests: `pytest portfolio/tests/test_frontend_allocations.py`
2. Tests should pass with minor timeout adjustments
3. Add new test for debouncing behavior

---

## Error Handling

### Client-Side (HTMX)
Add error indicator to form:
```html
<div id="htmx-error" class="alert alert-danger d-none">
    Error updating calculations. Please refresh.
</div>

<script>
document.body.addEventListener('htmx:responseError', (event) => {
    document.getElementById('htmx-error').classList.remove('d-none');
});
</script>
```

### Server-Side
In preview view:
```python
try:
    table_data = _calculate_preview_table_data(...)
except Exception as e:
    logger.exception("Error calculating allocation preview")
    return HttpResponse(
        "<div class='alert alert-danger'>Error calculating. Try again.</div>",
        status=500
    )
```

---

## Performance Considerations

1. **Debouncing:** 300ms delay prevents excessive requests
2. **Caching:** Consider caching user holdings/accounts during session
3. **Query Optimization:** Use `select_related()` and `prefetch_related()` in preview view
4. **Response Size:** Only return table HTML, not full page

---

## Future Enhancements (Optional)

1. **Loading Indicator:**
```html
<div class="htmx-indicator" id="calc-spinner">
    Calculating...
</div>
```

2. **Optimistic Updates:** Show changes immediately, then reconcile with server
3. **WebSocket:** For real-time collaboration (overkill for now)

---

## Files to Modify/Create

### Create:
- `portfolio/views/targets_preview.py` - New preview endpoint

### Modify:
- `portfolio/templates/base.html` - Add HTMX script
- `portfolio/templates/portfolio/_allocation_table.html` - Add HTMX attributes
- `portfolio/urls.py` - Add preview route
- `portfolio/tests/test_frontend_allocations.py` - Update test timeouts

### Reference (Don't Modify):
- `portfolio/services/target_allocations.py` - Reuse parsing/calculation logic
- `portfolio/models.py` - Read-only for current state

---

## Success Criteria

✅ User types in allocation input  
✅ After 300ms, table updates without page reload  
✅ Portfolio Total Target % updates correctly  
✅ Variance % updates correctly  
✅ Category Subtotals update correctly  
✅ Cash row updates (implicit allocation)  
✅ All Playwright tests pass  
✅ No errors in console  
✅ No N+1 query issues (check Django Debug Toolbar)  

---

## Rollback Plan

If HTMX approach has issues:
1. Remove HTMX script from base.html
2. Remove `hx-*` attributes from template
3. Delete preview endpoint
4. Revert to traditional form (submit button only)
5. Update tests to match traditional flow

The changes are minimal and isolated, making rollback easy.

---

## AI Agent Instructions

When implementing this plan:

1. **Start with Step 1-2:** Add HTMX and create the preview endpoint first
2. **Test endpoint independently:** Use curl/Postman to verify it returns correct HTML
3. **Then add Step 4:** Update template with HTMX attributes
4. **Test in browser:** Verify HTMX triggers and updates work
5. **Finally Step 7:** Update automated tests

**Key points:**
- Reuse existing calculation logic from `TargetAllocationService`
- DO NOT modify database in preview endpoint
- Keep preview endpoint fast (< 200ms response time)
- Add logging to debug calculation issues
- Follow existing code style and patterns in the project
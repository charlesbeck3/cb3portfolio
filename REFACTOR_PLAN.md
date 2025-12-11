# Portfolio Management Platform - Comprehensive OOP Refactoring Plan

## Executive Summary

This document outlines a comprehensive refactoring plan to transform the current Django-based portfolio management platform into a well-structured, maintainable codebase following OOP and modern software design best practices. The refactoring prioritizes incremental improvements that can be validated at each step while maintaining system stability.

---

## Current State Analysis

### Architecture Overview

The codebase is a Django 5.1 application with the following structure:

| Component | Current State | Issues |
|-----------|---------------|--------|
| **Models** (`models.py`) | 10 models with basic ORM relationships | Anemic domain models; business logic lives elsewhere |
| **Services** (`services.py`) | Single 600+ line file with `PortfolioSummaryService` | God class anti-pattern; mixed responsibilities |
| **Views** (`views.py`) | Class-based views with significant business logic | Fat views; duplicated code; tight coupling |
| **Structs** (`structs.py`) | Data classes for transfer objects | Good foundation; underutilized |
| **Managers** (`managers.py`) | Custom QuerySet managers | Solid pattern; could be extended |
| **Templates** | Complex HTML with embedded JavaScript | Heavy client-side calculations that mirror server logic |

### Key Pain Points

1. **God Class**: `PortfolioSummaryService` (600+ lines) handles pricing, target calculations, aggregations, sorting, and multiple summary types
2. **Anemic Domain Models**: Models are data containers with no behavior beyond `__str__` and `tax_treatment` property
3. **Procedural Code in Services**: Extensive use of dictionaries, manual iteration, and inline calculations
4. **View Layer Coupling**: Views directly manipulate data structures and contain business logic
5. **Duplicated Logic**: Target allocation calculations appear in multiple places (service, views, templates)
6. **Mixed Abstractions**: Same service returns different structures (`PortfolioSummary`, `dict[str, Any]`)

---

## Refactoring Principles

1. **Domain-Driven Design (DDD) Lite**: Introduce domain concepts without full DDD overhead
2. **Single Responsibility Principle**: Each class/module has one reason to change
3. **Rich Domain Models**: Move behavior to where the data lives
4. **Explicit Abstractions**: Define clear interfaces between layers
5. **Incremental Delivery**: Each phase produces working, tested code

---

## Design Decisions

### Money and Percentage Handling

We will use `Decimal` directly for all monetary and percentage values rather than creating wrapper value objects. Rationale:

1. **Single currency** - The application only handles USD, eliminating the primary benefit of Money classes (preventing currency mixing)
2. **Django integration** - `DecimalField` works seamlessly with Django ORM, admin, forms, and serialization
3. **Simplicity** - No conversion overhead at model boundaries
4. **Existing validation** - Django's `MinValueValidator`/`MaxValueValidator` already handle range constraints

**Standards for Decimal usage:**
- Monetary amounts: 2 decimal places for display, full precision for calculations
- Percentages: Stored as 0-100 scale (not 0-1), 2 decimal places
- Consistent type hints: `Decimal` throughout the codebase
- Template filters for formatting (not inline formatting logic)

### Where Domain Logic Lives

| Logic Type | Location | Example |
|------------|----------|---------|
| Single-record calculations | Model methods/properties | `Holding.market_value` |
| Allocation validation | `TargetAllocation` model | `target_value_for(account_total)` |
| Cross-record aggregation | Service layer | `AggregationService` |
| Multi-step orchestration | Service layer | `PortfolioSummaryService` |
| Request/response handling | Views | `DashboardView` |

---

## Agent Execution Instructions

This section provides explicit instructions for AI coding agents (Windsurf, Cursor, etc.) to execute this refactoring plan effectively.

### Pre-Execution Checklist

Before starting any phase, the agent should:

1. **Verify environment is working:**
   ```bash
   uv run python manage.py test
   uv run ruff check .
   uv run mypy portfolio/ --ignore-missing-imports
   ```

2. **Create a feature branch:**
   ```bash
   git checkout -b refactor/phase-N-description
   ```

3. **Understand current file locations:**
   - Models: `portfolio/models.py`
   - Services: `portfolio/services.py` (600+ lines, to be split)
   - Views: `portfolio/views.py`
   - Structs: `portfolio/structs.py`
   - Managers: `portfolio/managers.py`
   - Templates: `portfolio/templates/portfolio/`

### Execution Rules for All Phases

1. **Test after every file change** - Run `uv run python manage.py test` after creating/modifying any file
2. **Lint after every change** - Run `uv run ruff check . && uv run ruff format .`
3. **Type check after every change** - Run `uv run mypy portfolio/ --ignore-missing-imports`
4. **Small commits** - Commit after each logical unit (one class, one test file)
5. **Import order** - Use Django conventions: stdlib → django → third-party → local
6. **Type hints required** - All function signatures must have type hints
7. **Docstrings required** - All public classes and methods need docstrings

### Quick Validation Command

Run this combined command after every change:

```bash
uv run python manage.py test && uv run ruff check . && uv run ruff format . && uv run mypy portfolio/ --ignore-missing-imports
```

Or create an alias in your shell:

```bash
alias validate="uv run python manage.py test && uv run ruff check . && uv run ruff format . && uv run mypy portfolio/ --ignore-missing-imports"
```

### File Creation Commands

When creating new directories and files:

```bash
# Create domain directory structure
mkdir -p portfolio/domain
touch portfolio/domain/__init__.py

# Create services directory structure  
mkdir -p portfolio/services
touch portfolio/services/__init__.py

# Create views directory structure
mkdir -p portfolio/views
touch portfolio/views/__init__.py

# Create forms directory structure
mkdir -p portfolio/forms
touch portfolio/forms/__init__.py
```

### Phase-Specific Task Lists

#### Phase 1 Tasks (Execute in Order)

**Task 1.1: Create domain directory and AssetAllocation**
```
1. mkdir -p portfolio/domain && touch portfolio/domain/__init__.py
2. Create portfolio/domain/allocation.py with AssetAllocation class (copy from plan)
3. Create portfolio/tests/test_allocation.py with all tests
4. Run: uv run python manage.py test portfolio.tests.test_allocation
5. Run: uv run mypy portfolio/domain/ --ignore-missing-imports
6. Commit: "Add AssetAllocation value object"
```

**Task 1.2: Enhance Holding model**
```
1. Open portfolio/models.py
2. Add market_value property to Holding class
3. Add has_price property to Holding class
4. Add update_price() method to Holding class
5. Add calculate_target_value() method to Holding class
6. Add calculate_variance() method to Holding class
7. Add tests to portfolio/tests/test_models.py (create if not exists)
8. Run: uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports
9. Commit: "Add domain methods to Holding model"
```

**Task 1.3: Enhance Account model**
```
1. Open portfolio/models.py
2. Add total_value() method to Account class
3. Add holdings_by_asset_class() method to Account class
4. Add current_allocation() method that returns AssetAllocation
5. Add calculate_deviation() method
6. Add/update tests
7. Run: uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports
8. Commit: "Add domain methods to Account model"
```

**Task 1.4: Enhance TargetAllocation model**
```
1. Open portfolio/models.py
2. Add target_value_for() method
3. Add variance_for() method
4. Add variance_pct_for() method
5. Add to_asset_allocation() classmethod
6. Update validate_allocation_set() to work with AssetAllocation
7. Add/update tests
8. Run: uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports
9. Commit: "Add domain methods to TargetAllocation model"
```

**Task 1.5: Create Portfolio aggregate**
```
1. Create portfolio/domain/portfolio.py with Portfolio class
2. Add to portfolio/domain/__init__.py exports
3. Create portfolio/tests/test_portfolio.py
4. Run: uv run python manage.py test portfolio.tests.test_portfolio
5. Run: uv run mypy portfolio/domain/ --ignore-missing-imports
6. Commit: "Add Portfolio aggregate root"
```

**Task 1.6: Update __init__.py exports and final validation**
```
1. Update portfolio/domain/__init__.py:
   from portfolio.domain.allocation import AssetAllocation
   from portfolio.domain.portfolio import Portfolio
   __all__ = ['AssetAllocation', 'Portfolio']
2. Run full validation:
   uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports
3. Manual test: uv run python manage.py runserver (verify pages load)
4. Commit: "Complete Phase 1: Rich Domain Models"
```

#### Phase 2 Tasks (Execute in Order)

**Task 2.1: Create services directory structure**
```
1. mkdir -p portfolio/services
2. touch portfolio/services/__init__.py
3. Commit: "Create services directory structure"
```

**Task 2.2: Extract PricingService**
```
1. Create portfolio/services/pricing.py
2. Move update_prices logic from PortfolioSummaryService
3. Create portfolio/tests/test_services/__init__.py
4. Create portfolio/tests/test_services/test_pricing.py
5. Run: uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports
6. Commit: "Extract PricingService"
```

**Task 2.3: Extract TargetAllocationService**
```
1. Create portfolio/services/targets.py
2. Move get_effective_targets logic from PortfolioSummaryService
3. Update to return AssetAllocation objects (not dicts)
4. Create portfolio/tests/test_services/test_targets.py
5. Run: uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports
6. Commit: "Extract TargetAllocationService"
```

**Task 2.4: Create PortfolioAnalysis**
```
1. Create portfolio/domain/analysis.py
2. Add to portfolio/domain/__init__.py exports
3. Create portfolio/tests/test_analysis.py
4. Run: uv run python manage.py test portfolio.tests.test_analysis
5. Run: uv run mypy portfolio/domain/ --ignore-missing-imports
6. Commit: "Add PortfolioAnalysis domain object"
```

**Task 2.5: Refactor PortfolioSummaryService**
```
1. Create portfolio/services/summary.py
2. Import and use PricingService, TargetAllocationService, PortfolioAnalysis
3. Update portfolio/services/__init__.py with public exports:
   from portfolio.services.pricing import PricingService
   from portfolio.services.targets import TargetAllocationService
   from portfolio.services.summary import PortfolioSummaryService
   __all__ = ['PricingService', 'TargetAllocationService', 'PortfolioSummaryService']
4. Update imports in portfolio/views.py to use new service locations
5. Run: uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports
6. Manual test: uv run python manage.py runserver (verify all pages load)
7. Delete old portfolio/services.py after all tests pass
8. Run full validation again after deletion
9. Commit: "Complete Phase 2: Service decomposition"
```

### Verification Commands

After each phase, run these verification commands:

```bash
# Full test suite
uv run python manage.py test

# Lint check
uv run ruff check .

# Format check (auto-fixes formatting)
uv run ruff format .

# Type check (REQUIRED - catches type errors before runtime)
uv run mypy portfolio/ --ignore-missing-imports

# All-in-one validation (run this before every commit)
uv run python manage.py test && uv run ruff check . && uv run mypy portfolio/ --ignore-missing-imports

# Manual verification - start server and test UI
uv run python manage.py runserver
# Then visit http://127.0.0.1:8000/ and verify pages load correctly
```

### Common mypy Errors and Fixes

```python
# Error: Missing return type
def my_func(x):  # Bad
def my_func(x: int) -> str:  # Good

# Error: Incompatible types in assignment
result: str = some_func()  # If some_func returns int, mypy will catch this

# Error: has no attribute (often from untyped dict access)
data['key']  # If data is dict[str, Any], consider using TypedDict or a dataclass

# Error: Cannot find implementation or library stub
from some_lib import Thing  # Add to [tool.mypy] ignore_missing_imports or install stubs
```

### Error Recovery

If tests fail after a change:

1. **Don't proceed** - Fix the failing test first
2. **Check imports** - Most common issue is missing/wrong imports
3. **Check circular imports** - Use `TYPE_CHECKING` for type hints that cause cycles
4. **Revert if stuck** - `git checkout -- <file>` to undo changes

### Code Patterns to Follow

**Import pattern for domain objects:**
```python
from __future__ import annotations
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.models import Account
```

**Test pattern:**
```python
from decimal import Decimal
from django.test import TestCase

class MyDomainObjectTests(TestCase):
    def test_specific_behavior(self):
        # Arrange
        obj = MyObject(...)
        
        # Act
        result = obj.some_method()
        
        # Assert
        self.assertEqual(result, expected)
```

**Service pattern:**
```python
class MyService:
    """Docstring explaining responsibility."""
    
    def __init__(self, dependency: OtherService | None = None):
        self._dependency = dependency or OtherService()
    
    def do_something(self, user) -> ResultType:
        """Docstring explaining what this does."""
        # Implementation
```

### Files NOT to Modify (Until Specified)

- `portfolio/templates/` - Don't touch until Phase 4
- `portfolio/admin.py` - No changes needed
- `config/` - No changes needed
- `manage.py` - No changes needed
- `pyproject.toml` - No changes needed

### Success Criteria Per Phase

**Phase 1 Complete When:**
- [ ] `portfolio/domain/allocation.py` exists with `AssetAllocation` class
- [ ] `portfolio/domain/portfolio.py` exists with `Portfolio` class
- [ ] `Holding`, `Account`, `TargetAllocation` models have new methods
- [ ] All tests in `test_allocation.py`, `test_portfolio.py`, `test_models.py` pass
- [ ] `uv run python manage.py test` passes with no failures
- [ ] `uv run ruff check .` passes with no errors
- [ ] `uv run mypy portfolio/ --ignore-missing-imports` passes with no errors

**Phase 2 Complete When:**
- [ ] `portfolio/services/` directory exists with `pricing.py`, `targets.py`, `summary.py`
- [ ] `portfolio/domain/analysis.py` exists with `PortfolioAnalysis` class
- [ ] Old `portfolio/services.py` is deleted
- [ ] All views still work (manual test: pages load correctly)
- [ ] All tests pass
- [ ] Lint passes (`uv run ruff check .`)
- [ ] Type check passes (`uv run mypy portfolio/ --ignore-missing-imports`)

---

## Current Codebase Reference

This section documents the current state of key files for agent reference.

### Existing Model Methods to Preserve

The following methods/properties already exist in `portfolio/models.py` and should NOT be duplicated:

```python
# Account model
- __str__(self)
- @property tax_treatment (returns self.account_type.tax_treatment)

# Holding model  
- __str__(self)

# TargetAllocation model
- __str__(self)
```

### Existing Manager Methods

In `portfolio/managers.py`, these QuerySet methods exist:

```python
# HoldingManager / HoldingQuerySet
- get_for_pricing(user)      # Returns holdings for price updates
- get_for_summary(user)      # Returns holdings with select_related for summary view
- get_for_category_view(user) # Returns holdings for category grouping

# AccountManager / AccountQuerySet  
- get_summary_data(user)     # Returns accounts with prefetched holdings

# TargetAllocationManager
- (check file for current methods)
```

### Existing Service Methods to Replace

In `portfolio/services.py`, `PortfolioSummaryService` has these static methods:

```python
@staticmethod update_prices(user)           # → Move to PricingService
@staticmethod get_effective_targets(user)   # → Move to TargetAllocationService  
@staticmethod get_holdings_summary(user)    # → Refactor to use PortfolioAnalysis
@staticmethod get_holdings_by_category(user, account_id=None)  # → Keep or refactor
@staticmethod get_account_summary(user)     # → Keep for sidebar
# Plus several private helper methods (_build_category_maps, _aggregate_holdings, etc.)
```

### Existing Struct Classes

In `portfolio/structs.py`, these dataclasses exist and are used by views/templates:

```python
@dataclass AccountTypeData      # Per-account-type dollar/pct values
@dataclass AssetClassEntry      # Asset class with account type breakdown
@dataclass CategoryEntry        # Category grouping asset classes
@dataclass GroupEntry           # Top-level grouping
@dataclass PortfolioSummary     # Main summary structure (complex, nested)
@dataclass AggregatedHolding    # Holdings aggregated by ticker
@dataclass HoldingsCategory     # Category for holdings view
@dataclass HoldingsGroup        # Group for holdings view
@dataclass HoldingsSummary      # Summary for holdings view
```

**Note:** These structs are tightly coupled to templates. Phase 3-4 will simplify them, but Phase 1-2 should not break them.

### Import Statement Reference

When adding imports to existing files, follow this order:

```python
# portfolio/models.py imports (example)
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from portfolio.managers import (
    AccountManager,
    HoldingManager,
    TargetAllocationManager,
)
```

```python
# portfolio/services.py imports (example)
import logging
from collections import OrderedDict, defaultdict
from decimal import Decimal
from typing import Any

from portfolio.market_data import MarketDataService
from portfolio.models import Account, AssetCategory, Holding, TargetAllocation
from portfolio.structs import (
    AggregatedHolding,
    HoldingsCategory,
    HoldingsGroup,
    PortfolioSummary,
)
```

### Template Variables Expected

Views currently pass these context variables that templates expect:

```python
# DashboardView (index.html)
context['summary']      # PortfolioSummary instance
context['sidebar_data'] # Dict with account/group info

# TargetAllocationView (target_allocations.html)  
context['summary']           # PortfolioSummary instance
context['account_types']     # List of AccountType objects
context['asset_classes']     # List of AssetClass objects  
context['accounts']          # List of Account objects
context['defaults_map']      # {account_type_id: {asset_class_id: pct}}
context['overrides_map']     # {account_id: {asset_class_id: pct}}
context['sidebar_data']      # Dict with account/group info
```

**Important:** Until Phase 3-4, views must continue to provide these exact context variables.

---

## Phase 1: Rich Domain Models

**Duration**: 5-7 days  
**Risk**: Low-Medium  
**Goal**: Move behavior into model classes where data lives

**Duration**: 5-7 days  
**Risk**: Medium  
**Goal**: Move behavior into model classes

### 1.1 Enhance Holding Model

```python
# portfolio/models.py - Enhanced Holding

class Holding(models.Model):
    """Current investment holding in an account."""
    
    # ... existing fields ...
    
    # ===== Domain Methods =====
    
    @property
    def market_value(self) -> Decimal:
        """Current market value of this holding."""
        if self.current_price is None:
            return Decimal('0.00')
        return self.shares * self.current_price
    
    @property
    def has_price(self) -> bool:
        """Check if this holding has a current price."""
        return self.current_price is not None
    
    def update_price(self, new_price: Decimal) -> None:
        """Update the holding's price."""
        self.current_price = new_price
        self.save(update_fields=['current_price'])
    
    def calculate_target_value(self, account_total: Decimal, target_pct: Decimal) -> Decimal:
        """Calculate target value based on account total and target percentage."""
        return account_total * target_pct / Decimal('100')
    
    def calculate_variance(self, target_value: Decimal) -> Decimal:
        """Calculate variance from target (positive = overweight)."""
        return self.market_value - target_value
```

### 1.2 Enhance Account Model with Aggregate Methods

```python
# portfolio/models.py - Enhanced Account

class Account(models.Model):
    # ... existing fields ...
    
    # ===== Aggregate Methods =====
    
    def total_value(self) -> Decimal:
        """Calculate total market value of all holdings."""
        total = Decimal('0.00')
        for holding in self.holdings.all():
            total += holding.market_value
        return total
    
    def holdings_by_asset_class(self) -> dict[str, Decimal]:
        """Group holdings by asset class name and sum values."""
        result: dict[str, Decimal] = {}
        for holding in self.holdings.select_related('security__asset_class').all():
            ac_name = holding.security.asset_class.name
            result[ac_name] = result.get(ac_name, Decimal('0.00')) + holding.market_value
        return result
    
    def calculate_deviation(self, targets: dict[str, Decimal]) -> Decimal:
        """
        Calculate total absolute deviation from target allocation.
        
        Args:
            targets: Dict mapping asset class name to target percentage (0-100)
            
        Returns:
            Sum of |actual_value - target_value| for each asset class
        """
        account_total = self.total_value()
        holdings_by_ac = self.holdings_by_asset_class()
        
        total_deviation = Decimal('0.00')
        all_asset_classes = set(targets.keys()) | set(holdings_by_ac.keys())
        
        for ac_name in all_asset_classes:
            actual = holdings_by_ac.get(ac_name, Decimal('0.00'))
            target_pct = targets.get(ac_name, Decimal('0.00'))
            target_value = account_total * target_pct / Decimal('100')
            deviation = abs(actual - target_value)
            total_deviation += deviation
        
        return total_deviation
```

### 1.3 Enhance TargetAllocation Model

```python
# portfolio/models.py - Enhanced TargetAllocation

class TargetAllocation(models.Model):
    """Target allocation for a specific account type and asset class."""
    
    # ... existing fields ...
    
    # ===== Domain Methods =====
    
    def target_value_for(self, account_total: Decimal) -> Decimal:
        """Calculate the target dollar amount for a given account total."""
        return account_total * self.target_pct / Decimal('100')
    
    def variance_for(self, current_value: Decimal, account_total: Decimal) -> Decimal:
        """Calculate variance between current and target value."""
        target_value = self.target_value_for(account_total)
        return current_value - target_value
    
    def variance_pct_for(self, current_value: Decimal, account_total: Decimal) -> Decimal:
        """Calculate variance as a percentage of account total."""
        if account_total == 0:
            return Decimal('0.00')
        target_value = self.target_value_for(account_total)
        return (current_value - target_value) / account_total * Decimal('100')
    
    @classmethod
    def validate_allocation_set(cls, allocations: list['TargetAllocation']) -> tuple[bool, str]:
        """
        Validate that a set of allocations sums to 100% or less.
        
        Returns:
            (is_valid, error_message)
        """
        total = sum(a.target_pct for a in allocations)
        if total > Decimal('100.00'):
            return False, f"Allocations sum to {total}%, which exceeds 100%"
        return True, ""
```

### 1.4 Create Portfolio Aggregate Root

```python
# portfolio/domain/portfolio.py

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from portfolio.models import Account

@dataclass
class Portfolio:
    """
    Aggregate root representing a user's complete portfolio.
    Encapsulates all accounts and provides portfolio-level calculations.
    """
    user_id: int
    accounts: list[Account] = field(default_factory=list)
    
    def __iter__(self) -> Iterator[Account]:
        return iter(self.accounts)
    
    def __len__(self) -> int:
        return len(self.accounts)
    
    @property
    def total_value(self) -> Decimal:
        """Total value across all accounts."""
        return sum((acc.total_value() for acc in self.accounts), Decimal('0.00'))
    
    def value_by_account_type(self) -> dict[str, Decimal]:
        """Aggregate values by account type code."""
        result: dict[str, Decimal] = {}
        for account in self.accounts:
            code = account.account_type.code
            result[code] = result.get(code, Decimal('0.00')) + account.total_value()
        return result
    
    def value_by_asset_class(self) -> dict[str, Decimal]:
        """Aggregate values by asset class across all accounts."""
        result: dict[str, Decimal] = {}
        for account in self.accounts:
            for ac_name, value in account.holdings_by_asset_class().items():
                result[ac_name] = result.get(ac_name, Decimal('0.00')) + value
        return result
    
    def allocation_by_asset_class(self) -> dict[str, Decimal]:
        """
        Current allocation percentages by asset class.
        Returns: {asset_class_name: percentage} where percentages sum to 100
        """
        total = self.total_value
        if total == 0:
            return {}
        
        by_ac = self.value_by_asset_class()
        return {
            ac_name: value / total * Decimal('100')
            for ac_name, value in by_ac.items()
        }
    
    def variance_from_targets(
        self, 
        effective_targets: dict[int, dict[str, Decimal]]
    ) -> dict[str, Decimal]:
        """
        Calculate variance (current - target) by asset class across portfolio.
        
        Args:
            effective_targets: {account_id: {asset_class_name: target_pct}}
            
        Returns:
            {asset_class_name: variance_in_dollars}
        """
        # Calculate target dollars per asset class
        target_by_ac: dict[str, Decimal] = {}
        
        for account in self.accounts:
            account_total = account.total_value()
            account_targets = effective_targets.get(account.id, {})
            
            for ac_name, target_pct in account_targets.items():
                target_dollars = account_total * target_pct / Decimal('100')
                target_by_ac[ac_name] = target_by_ac.get(ac_name, Decimal('0.00')) + target_dollars
        
        # Calculate variance
        current_by_ac = self.value_by_asset_class()
        all_asset_classes = set(current_by_ac.keys()) | set(target_by_ac.keys())
        
        return {
            ac_name: current_by_ac.get(ac_name, Decimal('0.00')) - target_by_ac.get(ac_name, Decimal('0.00'))
            for ac_name in all_asset_classes
        }
    
    def account_by_id(self, account_id: int) -> Account | None:
        """Find an account by ID."""
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None
    
    def accounts_by_type(self, account_type_code: str) -> list[Account]:
        """Get all accounts of a specific type."""
        return [acc for acc in self.accounts if acc.account_type.code == account_type_code]
    
    @classmethod
    def load_for_user(cls, user) -> Portfolio:
        """Factory method to load a complete portfolio for a user."""
        from portfolio.models import Account
        accounts = list(Account.objects.get_summary_data(user))
        return cls(user_id=user.id, accounts=accounts)
```

### 1.5 Tests for Phase 1

```python
# portfolio/tests/test_models_domain.py
from decimal import Decimal
from django.test import TestCase
from portfolio.models import Account, Holding, TargetAllocation

class HoldingDomainTests(TestCase):
    def test_market_value_with_price(self):
        holding = Holding(shares=Decimal('10'), current_price=Decimal('100'))
        self.assertEqual(holding.market_value, Decimal('1000'))
    
    def test_market_value_no_price(self):
        holding = Holding(shares=Decimal('10'), current_price=None)
        self.assertEqual(holding.market_value, Decimal('0.00'))
    
    def test_calculate_variance(self):
        holding = Holding(shares=Decimal('10'), current_price=Decimal('100'))
        # Current value: 1000, Target: 800 -> Variance: +200 (overweight)
        variance = holding.calculate_variance(Decimal('800'))
        self.assertEqual(variance, Decimal('200'))


class AccountDomainTests(TestCase):
    def setUp(self):
        # Setup test data...
        pass
    
    def test_total_value(self):
        # Create account with holdings totaling $2000
        account = ...  # setup
        self.assertEqual(account.total_value(), Decimal('2000.00'))
    
    def test_calculate_deviation(self):
        # Account with $1000 total
        # Current: 60% stocks, 40% bonds
        # Target: 50% stocks, 50% bonds
        # Deviation: |600-500| + |400-500| = 100 + 100 = 200
        account = ...  # setup
        targets = {'US Stocks': Decimal('50'), 'Bonds': Decimal('50')}
        self.assertEqual(account.calculate_deviation(targets), Decimal('200'))


class TargetAllocationDomainTests(TestCase):
    def test_target_value_for(self):
        allocation = TargetAllocation(target_pct=Decimal('25'))
        target = allocation.target_value_for(Decimal('10000'))
        self.assertEqual(target, Decimal('2500'))
    
    def test_variance_for(self):
        allocation = TargetAllocation(target_pct=Decimal('25'))
        # Current: $3000, Target: 25% of $10000 = $2500
        # Variance: +$500 (overweight)
        variance = allocation.variance_for(Decimal('3000'), Decimal('10000'))
        self.assertEqual(variance, Decimal('500'))
    
    def test_validate_allocation_set_valid(self):
        allocations = [
            TargetAllocation(target_pct=Decimal('60')),
            TargetAllocation(target_pct=Decimal('40')),
        ]
        is_valid, msg = TargetAllocation.validate_allocation_set(allocations)
        self.assertTrue(is_valid)
    
    def test_validate_allocation_set_exceeds_100(self):
        allocations = [
            TargetAllocation(target_pct=Decimal('60')),
            TargetAllocation(target_pct=Decimal('50')),
        ]
        is_valid, msg = TargetAllocation.validate_allocation_set(allocations)
        self.assertFalse(is_valid)
        self.assertIn('110', msg)
```

---

## Phase 2: Service Layer Decomposition

**Duration**: 5-7 days  
**Risk**: Medium  
**Goal**: Break up the monolithic service into focused, single-responsibility services

### 2.1 Service Architecture

With aggregation logic living in domain objects (Portfolio, Account), the service layer is simple:

```
portfolio/services/
├── __init__.py              # Public API exports
├── pricing.py               # PricingService - fetches and updates prices
├── targets.py               # TargetAllocationService - resolves effective targets
└── summary.py               # PortfolioSummaryService - orchestrates and builds view models
```

The services focus on:
- **PricingService**: External API integration (yfinance)
- **TargetAllocationService**: Business rules for target resolution (defaults vs overrides)
- **PortfolioSummaryService**: Orchestration and building the `PortfolioSummary` struct for views

### 2.2 PricingService

```python
# portfolio/services/pricing.py

from decimal import Decimal
from portfolio.models import Holding
from portfolio.market_data import MarketDataService


class PricingService:
    """Fetches and updates security prices from external sources."""
    
    def __init__(self, market_data: MarketDataService | None = None):
        self._market_data = market_data or MarketDataService()
    
    def update_holdings_prices(self, user) -> dict[str, Decimal]:
        """
        Fetch current prices and update all holdings for a user.
        Returns map of ticker -> price for reference.
        """
        holdings = Holding.objects.get_for_pricing(user)
        tickers = list({h.security.ticker for h in holdings})
        
        if not tickers:
            return {}
        
        price_map = self._market_data.get_prices(tickers)
        
        for holding in holdings:
            ticker = holding.security.ticker
            if ticker in price_map:
                holding.update_price(price_map[ticker])
        
        return price_map
```

### 2.3 TargetAllocationService

```python
# portfolio/services/targets.py

from collections import defaultdict
from decimal import Decimal
from portfolio.models import Account, TargetAllocation


class TargetAllocationService:
    """
    Resolves effective target allocations for accounts.
    
    Target Resolution Strategy:
    1. Check for account-specific overrides
    2. If ANY override exists for account, use ONLY overrides (custom strategy)
    3. Otherwise, fall back to account type defaults
    """
    
    def get_effective_targets(self, user) -> dict[int, dict[str, Decimal]]:
        """
        Get effective target percentages for each account.
        
        Returns:
            {account_id: {asset_class_name: target_pct}}
        """
        targets = TargetAllocation.objects.filter(user=user).select_related(
            'account_type', 'asset_class', 'account'
        )
        
        # Build lookup structures
        type_defaults: dict[int, dict[str, Decimal]] = defaultdict(dict)
        account_overrides: dict[int, dict[str, Decimal]] = defaultdict(dict)
        
        for t in targets:
            ac_name = t.asset_class.name
            
            if t.account_id:
                account_overrides[t.account_id][ac_name] = t.target_pct
            else:
                type_defaults[t.account_type_id][ac_name] = t.target_pct
        
        # Resolve effective targets for each account
        accounts = Account.objects.filter(user=user).select_related('account_type')
        result: dict[int, dict[str, Decimal]] = {}
        
        for account in accounts:
            if account.id in account_overrides:
                # Custom strategy: use only overrides
                result[account.id] = dict(account_overrides[account.id])
            else:
                # Default strategy: use account type defaults
                defaults = type_defaults.get(account.account_type_id, {})
                result[account.id] = dict(defaults)
        
        return result
    
    def get_targets_for_account(self, user, account_id: int) -> dict[str, Decimal]:
        """Get effective targets for a single account."""
        all_targets = self.get_effective_targets(user)
        return all_targets.get(account_id, {})
```

### 2.4 PortfolioSummaryService

```python
# portfolio/services/summary.py

from decimal import Decimal
from portfolio.domain.portfolio import Portfolio
from portfolio.services.pricing import PricingService
from portfolio.services.targets import TargetAllocationService
from portfolio.structs import PortfolioSummary


class PortfolioSummaryService:
    """
    Orchestrates portfolio data retrieval and builds view models.
    
    Delegates to:
    - PricingService for price updates
    - TargetAllocationService for target resolution  
    - Portfolio aggregate for calculations
    """
    
    def __init__(
        self,
        pricing_service: PricingService | None = None,
        target_service: TargetAllocationService | None = None,
    ):
        self._pricing = pricing_service or PricingService()
        self._targets = target_service or TargetAllocationService()
    
    def get_holdings_summary(self, user) -> PortfolioSummary:
        """
        Generate a complete portfolio summary with all aggregations.
        """
        # 1. Update prices
        self._pricing.update_holdings_prices(user)
        
        # 2. Load portfolio aggregate
        portfolio = Portfolio.load_for_user(user)
        
        # 3. Get effective targets
        effective_targets = self._targets.get_effective_targets(user)
        
        # 4. Use Portfolio methods for calculations
        variance_by_ac = portfolio.variance_from_targets(effective_targets)
        
        # 5. Build the PortfolioSummary struct for view consumption
        return self._build_summary(portfolio, effective_targets)
    
    def _build_summary(
        self, 
        portfolio: Portfolio,
        effective_targets: dict[int, dict[str, Decimal]],
    ) -> PortfolioSummary:
        """
        Build the PortfolioSummary struct from Portfolio aggregate.
        Bridges domain objects to the existing template structure.
        """
        # Implementation uses portfolio methods:
        # - portfolio.total_value
        # - portfolio.value_by_asset_class()
        # - portfolio.value_by_account_type()
        # - portfolio.variance_from_targets(effective_targets)
        # - account.total_value()
        # - account.holdings_by_asset_class()
        ...
    
    def update_prices(self, user) -> None:
        """Update prices for all user holdings."""
        self._pricing.update_holdings_prices(user)
    
    def get_effective_targets(self, user) -> dict[int, dict[str, Decimal]]:
        """Get resolved target allocations."""
        return self._targets.get_effective_targets(user)
```

---

## Phase 3: View Layer Refactoring

**Duration**: 5-7 days  
**Risk**: Medium  
**Goal**: Thin views that delegate to services

### 3.1 View Mixins

```python
# portfolio/views/mixins.py

from portfolio.services import PortfolioSummaryService, TargetAllocationService

class PortfolioContextMixin:
    """Provides common portfolio context data."""
    
    def get_portfolio_services(self):
        if not hasattr(self, '_services'):
            self._services = {
                'summary': PortfolioSummaryService(),
                'targets': TargetAllocationService(),
            }
        return self._services
    
    def get_sidebar_context(self, user):
        """Get sidebar data for all portfolio views."""
        service = self.get_portfolio_services()['summary']
        return {'sidebar_data': service.get_account_summary(user)}
```

### 3.2 Simplified Views

```python
# portfolio/views/dashboard.py

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from portfolio.views.mixins import PortfolioContextMixin

class DashboardView(LoginRequiredMixin, PortfolioContextMixin, TemplateView):
    template_name = 'portfolio/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        services = self.get_portfolio_services()
        
        # Get summary (single service call does all work)
        summary = services['summary'].get_holdings_summary(user)
        
        context.update({
            'summary': summary,
            'sidebar_data': services['summary'].get_account_summary(user),
            'portfolio_total_value': summary.grand_total,
        })
        
        return context
```

### 3.3 Form Handling Extraction

```python
# portfolio/forms.py

from django import forms
from decimal import Decimal

class TargetAllocationForm(forms.Form):
    """Handles target allocation form submission."""
    
    def __init__(self, *args, account_types=None, asset_classes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.account_types = account_types or []
        self.asset_classes = asset_classes or []
        
        # Dynamically add fields for each account type / asset class combo
        for at in self.account_types:
            for ac in self.asset_classes:
                field_name = f'target_{at.id}_{ac.id}'
                self.fields[field_name] = forms.DecimalField(
                    required=False,
                    min_value=0,
                    max_value=100,
                    decimal_places=2,
                )
    
    def get_parsed_targets(self) -> dict[int, dict[int, Decimal]]:
        """Parse form data into structured target allocations."""
        result: dict[int, dict[int, Decimal]] = {}
        
        for at in self.account_types:
            result[at.id] = {}
            total = Decimal('0')
            
            for ac in self.asset_classes:
                field_name = f'target_{at.id}_{ac.id}'
                value = self.cleaned_data.get(field_name) or Decimal('0')
                result[at.id][ac.id] = value
                total += value
            
            # Calculate cash residual
            cash_residual = max(Decimal('0'), Decimal('100') - total)
            # Store cash separately or with cash AC id
            
        return result
```

---

## Phase 4: Template Simplification

**Duration**: 3-5 days  
**Risk**: Medium  
**Goal**: Move calculations to backend, simplify templates

### 4.1 Pre-Computed Template Context

Instead of complex template logic with filters and calculations, compute everything in Python:

```python
# portfolio/views/context_builders.py

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class AllocationTableRow:
    """Pre-computed data for a single allocation table row."""
    asset_class_id: int
    asset_class_name: str
    category_code: str
    is_subtotal: bool = False
    
    # Account type columns (list for iteration in template)
    account_type_data: list['AccountTypeColumnData']
    
    # Portfolio totals - pre-formatted strings
    portfolio_current: str
    portfolio_target: str
    portfolio_variance: str
    variance_css_class: str  # 'text-success', 'text-danger', or ''


@dataclass
class AccountTypeColumnData:
    """Pre-computed data for one account type column."""
    code: str
    label: str
    
    # Pre-formatted for display
    current: str
    target: str
    variance: str
    variance_css_class: str
    
    # Raw values if JS needs them
    current_raw: Decimal
    target_raw: Decimal
    variance_raw: Decimal


class AllocationTableBuilder:
    """Builds pre-computed context for allocation tables."""
    
    def __init__(self, format_money: callable, format_percent: callable):
        self._format_money = format_money
        self._format_percent = format_percent
    
    def build_rows(
        self, 
        summary: 'PortfolioSummary', 
        account_types: list,
        mode: str = 'money'  # 'money' or 'percent'
    ) -> list[AllocationTableRow]:
        """Build all rows for the allocation table."""
        rows = []
        
        for group_code, group_data in summary.groups.items():
            for cat_code, cat_data in group_data.categories.items():
                for ac_name, ac_data in cat_data.asset_classes.items():
                    row = self._build_asset_row(
                        ac_name, ac_data, account_types, summary, mode
                    )
                    rows.append(row)
                
                # Add category subtotal row if multiple asset classes
                if len(cat_data.asset_classes) > 1:
                    rows.append(self._build_subtotal_row(
                        cat_code, cat_data, account_types, mode
                    ))
        
        return rows
    
    def _build_asset_row(
        self, ac_name, ac_data, account_types, summary, mode
    ) -> AllocationTableRow:
        """Build a single asset class row."""
        at_columns = []
        
        for at in account_types:
            at_data = ac_data.account_types.get(at.code)
            if at_data:
                at_columns.append(AccountTypeColumnData(
                    code=at.code,
                    label=at.label,
                    current=self._format_value(at_data.current, mode),
                    target=self._format_value(at_data.target, mode),
                    variance=self._format_value(at_data.variance, mode),
                    variance_css_class=self._variance_class(at_data.variance),
                    current_raw=at_data.current,
                    target_raw=at_data.target,
                    variance_raw=at_data.variance,
                ))
            else:
                at_columns.append(self._empty_column(at))
        
        return AllocationTableRow(
            asset_class_id=ac_data.id or 0,
            asset_class_name=ac_name,
            category_code=getattr(ac_data, 'category_code', ''),
            account_type_data=at_columns,
            portfolio_current=self._format_value(ac_data.total, mode),
            portfolio_target=self._format_value(ac_data.target_total, mode),
            portfolio_variance=self._format_value(ac_data.variance_total, mode),
            variance_css_class=self._variance_class(ac_data.variance_total),
        )
    
    def _format_value(self, value: Decimal, mode: str) -> str:
        if mode == 'percent':
            return self._format_percent(value)
        return self._format_money(value)
    
    def _variance_class(self, variance: Decimal) -> str:
        if variance > 0:
            return 'text-success'
        elif variance < 0:
            return 'text-danger'
        return ''
    
    def _empty_column(self, at) -> AccountTypeColumnData:
        return AccountTypeColumnData(
            code=at.code,
            label=at.label,
            current='--',
            target='--', 
            variance='--',
            variance_css_class='',
            current_raw=Decimal('0'),
            target_raw=Decimal('0'),
            variance_raw=Decimal('0'),
        )
```

### 4.2 Simplified Template

```html
<!-- portfolio/templates/portfolio/includes/allocation_table_simple.html -->

<table class="table table-sm">
    <thead>
        <tr>
            <th>Asset Class</th>
            {% for at in account_types %}
                <th colspan="3" class="text-center">{{ at.label }}</th>
            {% endfor %}
            <th colspan="3" class="text-center table-active">Portfolio</th>
        </tr>
        <tr>
            <th></th>
            {% for at in account_types %}
                <th class="text-end small text-muted">Current</th>
                <th class="text-end small text-muted">Target</th>
                <th class="text-end small text-muted">Var</th>
            {% endfor %}
            <th class="text-end small text-muted table-active">Current</th>
            <th class="text-end small text-muted table-active">Target</th>
            <th class="text-end small text-muted table-active">Var</th>
        </tr>
    </thead>
    <tbody>
        {% for row in allocation_rows %}
        <tr data-ac-id="{{ row.asset_class_id }}"
            {% if row.is_subtotal %}class="table-secondary fw-bold"{% endif %}>
            <td class="ps-4">{{ row.asset_class_name }}</td>
            
            {% for at_col in row.account_type_data %}
                <td class="text-end">{{ at_col.current }}</td>
                <td class="text-end">{{ at_col.target }}</td>
                <td class="text-end {{ at_col.variance_css_class }}">{{ at_col.variance }}</td>
            {% endfor %}
            
            <td class="text-end table-active">{{ row.portfolio_current }}</td>
            <td class="text-end table-active">{{ row.portfolio_target }}</td>
            <td class="text-end table-active {{ row.variance_css_class }}">{{ row.portfolio_variance }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
```

### 4.3 Consolidated Template Filters

```python
# portfolio/templatetags/portfolio_filters.py

from decimal import Decimal
from django import template

register = template.Library()


@register.filter
def accounting_money(value: Decimal | None, decimal_places: int = 0) -> str:
    """
    Format a decimal as accounting-style money.
    Negative values shown in parentheses: ($1,234)
    """
    if value is None:
        return '--'
    
    try:
        value = Decimal(str(value))
    except (ValueError, TypeError):
        return '--'
    
    is_negative = value < 0
    abs_value = abs(value)
    
    if decimal_places == 0:
        formatted = f'{abs_value:,.0f}'
    else:
        formatted = f'{abs_value:,.{decimal_places}f}'
    
    if is_negative:
        return f'(${formatted})'
    return f'${formatted}'


@register.filter
def accounting_percent(value: Decimal | None, decimal_places: int = 1) -> str:
    """
    Format a decimal as accounting-style percentage.
    Negative values shown in parentheses: (5.2%)
    """
    if value is None:
        return '--'
    
    try:
        value = Decimal(str(value))
    except (ValueError, TypeError):
        return '--'
    
    is_negative = value < 0
    abs_value = abs(value)
    
    formatted = f'{abs_value:.{decimal_places}f}%'
    
    if is_negative:
        return f'({formatted})'
    return formatted


@register.filter  
def variance_class(value: Decimal | None) -> str:
    """Return CSS class based on variance sign."""
    if value is None:
        return ''
    try:
        value = Decimal(str(value))
        if value > 0:
            return 'text-success'
        elif value < 0:
            return 'text-danger'
    except (ValueError, TypeError):
        pass
    return ''
```

---

## Implementation Roadmap

### Sprint 1 (Weeks 1-2): Rich Domain Models
- [ ] Phase 1: Add domain methods to Holding, Account, TargetAllocation
- [ ] Create Portfolio aggregate root with aggregation methods
- [ ] Unit tests for model domain methods
- [ ] Unit tests for Portfolio aggregate
- [ ] Verify existing tests still pass

### Sprint 2 (Weeks 3-4): Service Decomposition
- [ ] Phase 2: Extract PricingService
- [ ] Extract TargetAllocationService
- [ ] Refactor PortfolioSummaryService to use Portfolio aggregate
- [ ] Integration tests

### Sprint 3 (Weeks 5-6): Views & Forms
- [ ] Phase 3: Create view mixins
- [ ] Simplify DashboardView
- [ ] Simplify TargetAllocationView
- [ ] Extract form handling
- [ ] View tests

### Sprint 4 (Weeks 7-8): Templates & Polish
- [ ] Phase 4: Create AllocationTableBuilder
- [ ] Simplify allocation templates
- [ ] Consolidate template filters
- [ ] End-to-end tests
- [ ] Documentation

---

## Migration Strategy

Since this is a personal application without production traffic, we can refactor directly:

1. **Work in feature branches** - One branch per phase for clean commits
2. **Run tests after each change** - Catch regressions immediately
3. **Refactor incrementally** - Small commits that can be bisected if issues arise
4. **Delete old code immediately** - No need to maintain parallel implementations

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| `services.py` line count | 600+ | <150 per file |
| Cyclomatic complexity (max) | ~20 | <10 |
| Test coverage (services) | ~60% | >90% |
| View method length | ~100 lines | <30 lines |
| Template logic | Heavy JS | Minimal JS |
| Domain objects | 0 | 4 (Portfolio, AssetAllocation, PortfolioAnalysis, RebalancingPlan) |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Comprehensive test suite before refactoring |
| Performance regression | Benchmark before/after each phase |
| Scope creep | Strict phase boundaries, defer enhancements |
| Over-engineering | Start simple, add complexity only when needed |
| Feature delay | Core refactoring enables features, not blocks them |

---

## Appendix A: File Structure After Refactoring

```
portfolio/
├── domain/
│   ├── __init__.py
│   ├── allocation.py          # AssetAllocation value object
│   ├── portfolio.py           # Portfolio aggregate root
│   └── analysis.py            # PortfolioAnalysis
├── services/
│   ├── __init__.py            # Public API exports
│   ├── pricing.py             # PricingService
│   ├── targets.py             # TargetAllocationService
│   └── summary.py             # PortfolioSummaryService (orchestrator)
├── views/
│   ├── __init__.py
│   ├── mixins.py              # PortfolioContextMixin
│   ├── context_builders.py    # AllocationTableBuilder
│   ├── dashboard.py           # DashboardView
│   ├── holdings.py            # HoldingsView
│   └── targets.py             # TargetAllocationView
├── forms/
│   ├── __init__.py
│   └── allocations.py         # TargetAllocationForm
├── templatetags/
│   └── portfolio_filters.py   # Consolidated filters
├── models.py                  # Enhanced with domain methods
├── managers.py                # Existing QuerySet managers
├── structs.py                 # Data transfer objects for views
├── market_data.py             # MarketDataService (yfinance wrapper)
└── tests/
    ├── test_models.py         # Model + domain method tests
    ├── test_allocation.py     # AssetAllocation tests
    ├── test_portfolio.py      # Portfolio aggregate tests
    ├── test_analysis.py       # PortfolioAnalysis tests
    ├── test_services/
    │   ├── __init__.py
    │   ├── test_pricing.py
    │   └── test_targets.py
    └── test_views.py
```

## Appendix B: Future File Structure (After All Phases)

```
portfolio/
├── domain/
│   ├── __init__.py
│   ├── allocation.py          # AssetAllocation value object
│   ├── portfolio.py           # Portfolio aggregate root
│   ├── analysis.py            # PortfolioAnalysis
│   └── rebalancing.py         # RebalancingPlan, RebalancingTrade
├── analytics/                  # Phase 6
│   ├── __init__.py
│   ├── models.py              # SecurityPrice
│   ├── timeseries.py          # Return calculations, correlations
│   ├── backtester.py          # Backtest engine
│   └── metrics.py             # Sharpe, Sortino, drawdown
├── services/
│   ├── __init__.py
│   ├── pricing.py             # PricingService
│   ├── targets.py             # TargetAllocationService
│   ├── summary.py             # PortfolioSummaryService
│   └── rebalancing.py         # RebalancingService (Phase 5)
├── views/
│   ├── __init__.py
│   ├── mixins.py
│   ├── context_builders.py
│   ├── dashboard.py
│   ├── holdings.py
│   ├── targets.py
│   ├── rebalancing.py         # Phase 5
│   └── analytics.py           # Phase 6
├── forms/
│   ├── __init__.py
│   ├── allocations.py
│   └── strategy.py            # Phase 7
├── templatetags/
│   └── portfolio_filters.py
├── models.py                  # + AllocationStrategy, AllocationStrategyDetail (Phase 7)
├── managers.py
├── structs.py
├── market_data.py
└── tests/
    ├── ...existing...
    ├── test_rebalancing.py    # Phase 5
    └── analytics/             # Phase 6
        ├── test_backtester.py
        └── test_metrics.py
```

## Appendix C: Key Domain Object Summary

### AssetAllocation (Value Object)
- **Purpose**: Immutable allocation specification decoupled from accounts
- **Key Methods**: `apply_to(total)`, `variance_from(other)`, `merge_with(other)`
- **Used By**: TargetAllocationService, PortfolioAnalysis, Backtester

### Portfolio (Aggregate Root)
- **Purpose**: Represent current portfolio state
- **Key Methods**: `total_value`, `value_by_asset_class()`, `current_allocation()`
- **Used By**: PortfolioAnalysis, views

### PortfolioAnalysis (Analysis Object)
- **Purpose**: Combine Portfolio with targets for analysis
- **Key Methods**: `variance_by_asset_class()`, `accounts_needing_rebalance()`
- **Used By**: Views, RebalancingService

### RebalancingPlan (Future)
- **Purpose**: Proposed trades to rebalance
- **Key Properties**: `trades`, `net_cash_flow`, `total_trade_value`
- **Used By**: RebalancingService, rebalancing views

## Appendix D: Design Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Money value object | No | Single currency (USD), Django Decimal works well |
| Percentage value object | No | Simple validation, no complex operations needed |
| AssetAllocation value object | Yes | Decoupled from persistence, self-validating, used across features |
| Portfolio as Django model | No | No need to persist, aggregate is read-only view |
| PortfolioAnalysis separate from Portfolio | Yes | Separates "what I have" from "what I'm targeting" |
| Services return domain objects | Yes | `TargetAllocationService` returns `AssetAllocation`, not dicts |
| AllocationStrategy model | Deferred to Phase 7 | Build foundation first, add persistence later |---------|--------|
| `services.py` line count | 600+ | <150 per file |
| Cyclomatic complexity (max) | ~20 | <10 |
| Test coverage (services) | ~60% | >90% |
| View method length | ~100 lines | <30 lines |
| Template logic | Heavy JS | Minimal JS |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Comprehensive test suite before refactoring |
| Performance regression | Benchmark before/after each phase |
| Team adoption | Clear documentation, pair programming |
| Scope creep | Strict phase boundaries, defer enhancements |

---

## Appendix: File Structure After Refactoring

```
portfolio/
├── domain/
│   ├── __init__.py
│   └── portfolio.py           # Portfolio aggregate root
├── services/
│   ├── __init__.py            # Public API exports
│   ├── pricing.py             # PricingService
│   ├── targets.py             # TargetAllocationService
│   └── summary.py             # PortfolioSummaryService (orchestrator)
├── views/
│   ├── __init__.py
│   ├── mixins.py              # PortfolioContextMixin
│   ├── context_builders.py    # AllocationTableBuilder
│   ├── dashboard.py           # DashboardView
│   ├── holdings.py            # HoldingsView
│   └── targets.py             # TargetAllocationView
├── forms/
│   ├── __init__.py
│   └── allocations.py         # TargetAllocationForm
├── templatetags/
│   └── portfolio_filters.py   # Consolidated filters
├── models.py                  # Enhanced with domain methods
├── managers.py                # Existing QuerySet managers
├── structs.py                 # Data transfer objects for views
├── market_data.py             # MarketDataService (yfinance wrapper)
└── tests/
    ├── test_models.py         # Model + domain method tests
    ├── test_portfolio.py      # Portfolio aggregate tests
    ├── test_services/
    │   ├── __init__.py
    │   ├── test_pricing.py
    │   └── test_targets.py
    └── test_views.py
```
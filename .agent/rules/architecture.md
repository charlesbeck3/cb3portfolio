---
trigger: always_on
---

# Architecture Principles for cb3portfolio

## Project Context

This is cb3portfolio, a Django-based personal portfolio management platform focused on tax-optimized investment management with asset location optimization and automated rebalancing capabilities. This is a **single-user personal tool**, not a multi-tenant SaaS application.

## Core Architectural Principles

### 1. Django-Native First

**ALWAYS prefer Django's built-in solutions over external dependencies.**

- Use Django's native features (e.g., native CSP support in Django 6.0)
- Only add external dependencies when Django doesn't provide the capability
- Avoid heavy frameworks or abstractions when Django can handle it
- Check Django documentation first before adding packages

### 2. Domain-Driven Design

**Business logic belongs in domain models, not views or templates.**

- Domain models enforce business constraints (e.g., allocation percentages sum to 100%)
- Services handle orchestration and external integrations
- Clear separation of concerns:
  - **Domain Models** - Business entities and rules
  - **Services** - Orchestration and coordination
  - **Views** - HTTP handling only
  - **Templates** - Presentation only

**Layer Flow:**
```
Domain Models → Services → Views → Templates
```

### 3. Calculation Architecture

**All financial calculations use pandas DataFrames with MultiIndex structures.**

- Centralize calculations in Engine classes (e.g., `AllocationEngine`)
- Separate calculation logic from presentation formatting
- **Pattern:** Engine → Formatter for all data presentation
- Use Python's `Decimal` type for monetary precision
- Never use `float` for money calculations

**Calculation Flow:**
```
Engine (pandas calculations) → Formatter (presentation) → View → Template
```

### 4. Simplicity Over Complexity

- Prefer simple, maintainable solutions
- Avoid premature optimization
- Choose well-maintained dependencies over complex custom solutions
- Consolidate documentation in README.md (single source of truth)
- Don't create separate architecture documents - keep it in README

### 5. Comprehensive Testing

- Comprehensive test coverage is non-negotiable (~94% target)
- **Golden reference tests with real-world data scenarios for financial calculations**
- Test hierarchy: Unit → Integration → E2E
- Tests written alongside or after implementation
- Financial calculation errors could result in material losses - tests provide confidence

## File Organization

```
cb3portfolio/
├── domain/          # Domain models and business logic
│   ├── models.py    # Django models with business methods
│   └── services.py  # Domain services
├── engines/         # Calculation engines (pandas-based)
│   ├── base.py      # Base engine classes
│   └── allocation.py
├── formatters/      # Presentation formatters
│   └── allocation.py
├── views.py         # Django views (thin, orchestration only)
├── urls.py
└── templates/       # Django templates
```

## Technology Stack

- **Python:** 3.12+
- **Framework:** Django 6.0
- **Calculations:** pandas (with MultiIndex)
- **Database:** SQLite (dev/test), PostgreSQL (production consideration)
- **Package Management:** uv
- **Linting/Formatting:** ruff
- **Type Checking:** mypy
- **Testing:** pytest
- **E2E Testing:** Playwright

## Key Design Decisions

### Why Django-Native First?
- Reduces dependencies
- Leverages framework capabilities
- Better long-term maintenance
- Built-in security features

### Why Domain-Driven Design?
- Clear separation of concerns
- Business logic in appropriate places
- Easier to test
- Better code organization

### Why Pandas for Calculations?
- 10-20x performance improvement via vectorization
- Natural fit for financial data
- MultiIndex for hierarchical aggregations
- Industry standard for data analysis

### Why Single-User Focus?
- Simpler architecture
- No multi-tenancy complexity
- Faster development
- Personal tool optimization

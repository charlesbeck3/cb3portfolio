---
trigger: always_on
---

Run the ruff and mypy linting agents for the entire repository and fix all outstanding issues after making any changes.  The commands are below


`uv run ruff check . --fix`

`uv run mypy .`
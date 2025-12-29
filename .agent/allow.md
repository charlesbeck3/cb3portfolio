# Allowed Commands

## Code Quality Tools
uv run ruff format .
uv run ruff check .
uv run ruff check --fix
uv run mypy .

## Testing (safe)
uv run pytest
uv run pytest -q
uv run pytest -v
uv run pytest -x
uv run pytest --maxfail=1
uv run pytest -s
uv run pytest -k test_name
uv run pytest --cov
uv run pytest --cov --cov-fail-under=90

## Testing (explicit paths)
uv run pytest portfolio/tests/services/test_allocation_presentation.py

## Coverage output (read-only/reporting)
uv run coverage report
uv run coverage html

## Safe shell (read-only inspection)
pwd
ls
ls -la
ls portfolio

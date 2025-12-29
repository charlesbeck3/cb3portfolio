# Allowed Commands

## Code Quality Tools
uv run ruff format .
uv run ruff check .
uv run mypy .

## Testing
uv run pytest
uv run pytest --cov
uv run pytest --cov --cov-fail-under=90

## Alternative forms (if agent uses variations)
uv run ruff format
uv run ruff check
uv run pytest --cov --cov-fail-under=90
uv run ruff check --fix
uv run pytest -v
uv run pytest -k test_name
uv run coverage report
uv run coverage html

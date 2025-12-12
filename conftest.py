import os


def pytest_configure() -> None:
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

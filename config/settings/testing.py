from .base import *  # noqa: F403

DEBUG = False

# Use a fast password hasher for testing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use in-memory SQLite for speed
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable logging during tests to keep output clean(er)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "portfolio": {
            "handlers": ["console"],
            "level": "CRITICAL",
        },
    },
}

# Use default StaticFilesStorage for tests to avoid manifest requirements
# This prevents "ValueError: Missing staticfiles manifest entry" in CI
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

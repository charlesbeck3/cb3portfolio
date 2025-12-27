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

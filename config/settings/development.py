from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Simplify password validation for development
AUTH_PASSWORD_VALIDATORS = []

# Add debug toolbar if installed
try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass

# Development-specific logging: verbose output with colors
from config.logging import get_logging_config  # noqa: E402

LOGGING = get_logging_config(debug=True)
# Set portfolio logging to DEBUG for development
LOGGING["loggers"]["portfolio"]["level"] = "DEBUG"

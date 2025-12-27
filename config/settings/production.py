"""
Production settings for cb3portfolio.

SECURITY WARNING: This configuration is for production environments only.
Ensure all environment variables are properly set before deployment.
"""

import os

from .base import *  # noqa: F403

# ============================================================================
# SECURITY SETTINGS
# ============================================================================

DEBUG = False

# Required: Must be set via environment variable
SECRET_KEY = os.getenv("SECRET_KEY", "")  # noqa: F405
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set in production")

# Required: Comma-separated list of allowed hosts
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]  # noqa: F405
if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS must be set in production")

# ... (rest of file) ...

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

from config.logging import get_logging_config  # noqa: E402

LOGGING = get_logging_config(debug=False)

# Production-specific enhancements: Add file handlers with rotation
LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "application.log",  # noqa: F405
    "maxBytes": 10 * 1024 * 1024,  # 10MB
    "backupCount": 5,
    "formatter": "json",
    "level": "INFO",
}

LOGGING["handlers"]["error_file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "errors.log",  # noqa: F405
    "maxBytes": 10 * 1024 * 1024,  # 10MB
    "backupCount": 5,
    "formatter": "json",
    "level": "ERROR",
}

# Add file handlers to root and portfolio loggers
LOGGING["root"]["handlers"] = ["console", "file"]
LOGGING["loggers"]["portfolio"]["handlers"] = ["console", "file"]

# Email admins on ERROR (requires EMAIL_* settings to be configured)
if os.getenv("EMAIL_HOST"):  # noqa: F405
    LOGGING["handlers"]["mail_admins"] = {
        "level": "ERROR",
        "class": "django.utils.log.AdminEmailHandler",
        "include_html": True,
    }
    LOGGING["loggers"]["django.request"]["handlers"] = ["console", "file", "mail_admins"]


# ============================================================================
# PERFORMANCE OPTIMIZATION
# ============================================================================

# Template caching
TEMPLATES[0]["OPTIONS"]["loaders"] = [  # type: ignore # noqa: F405
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    ),
]

# Disable debug toolbar in production
if "debug_toolbar" in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS.remove("debug_toolbar")  # noqa: F405
    MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa: F405

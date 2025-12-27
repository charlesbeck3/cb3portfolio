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

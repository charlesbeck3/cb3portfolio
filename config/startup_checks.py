"""
Startup validation checks for production environment.

Validates that all required configuration is present before the application starts.
This provides fast failure with clear error messages rather than cryptic runtime errors.
"""

import os

from django.core.exceptions import ImproperlyConfigured


def validate_production_config() -> None:
    """
    Validate all required environment variables for production deployment.

    Raises:
        ImproperlyConfigured: If any required environment variables are missing.

    Usage:
        # In config/settings/production.py, after imports:
        from config.startup_checks import validate_production_config
        validate_production_config()
    """
    required_vars = [
        "SECRET_KEY",
        "ALLOWED_HOSTS",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ]

    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        raise ImproperlyConfigured(
            f"Missing required environment variables for production: {', '.join(missing)}\n"
            f"Please set these in your environment or .env file.\n"
            f"See .env.example for reference."
        )

    # Validate ALLOWED_HOSTS is not empty after splitting
    allowed_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not allowed_hosts:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS environment variable must contain at least one hostname"
        )

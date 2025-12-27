"""
Application logging configuration.

Provides structured JSON logging in production and human-readable
console output in development using structlog.

Usage:
    from config.logging import configure_structlog, get_logging_config

    # Early in settings initialization
    configure_structlog(debug=True)

    # When defining LOGGING setting
    LOGGING = get_logging_config(debug=True)
"""

import sys
from typing import Any

import structlog


def configure_structlog(debug: bool = False) -> None:
    """
    Configure structlog for the application.

    Must be called early in settings initialization, before any logging occurs.

    Args:
        debug: If True, use pretty console output with colors.
               If False, use JSON output for log aggregation.

    Example:
        # In config/settings/base.py
        from config.logging import configure_structlog
        configure_structlog(debug=DEBUG)
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if debug:
        # Development: Pretty console output with colors
        processors = shared_processors + [structlog.dev.ConsoleRenderer(colors=True)]
    else:
        # Production: JSON output for log aggregation
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,  # type: ignore
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logging_config(debug: bool = False) -> dict[str, Any]:
    """
    Return Django LOGGING configuration dict.

    Separates Django's logging config from structlog's config for better
    maintainability and per-environment customization.

    Args:
        debug: If True, use console formatter with colors.
               If False, use JSON formatter for production.

    Returns:
        Django LOGGING configuration dict ready for use in settings.

    Example:
        # In config/settings/base.py
        from config.logging import get_logging_config
        LOGGING = get_logging_config(debug=DEBUG)

        # In config/settings/production.py
        LOGGING = get_logging_config(debug=False)
        # Customize by adding file handlers, etc.
    """
    formatter = "console" if debug else "json"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
                "foreign_pre_chain": [
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="iso", utc=True),
                ],
            },
            "console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(colors=True),
                "foreign_pre_chain": [
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="iso", utc=True),
                ],
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": formatter,
                "stream": sys.stdout,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "loggers": {
            "portfolio": {
                "handlers": ["console"],
                "level": "DEBUG" if debug else "INFO",
                "propagate": False,
            },
            "portfolio.services": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "portfolio.views": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "django": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "django.security": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

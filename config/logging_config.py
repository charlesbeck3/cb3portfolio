"""
Structured logging configuration using structlog.

Provides JSON logging in production and pretty console logs in development.
"""

from django.conf import settings

import structlog


def configure_structlog() -> None:
    """
    Configure structlog for Django application.

    - Development: Pretty console output with colors
    - Production: JSON output for log aggregation
    """

    # Shared processors for all environments
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    # Environment-specific processors
    if settings.DEBUG:
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
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

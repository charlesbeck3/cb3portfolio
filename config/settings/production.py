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
SECRET_KEY = os.getenv("SECRET_KEY")  # noqa: F405
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set in production")

# Required: Comma-separated list of allowed hosts
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]  # noqa: F405
if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS must be set in production")

# Security middleware settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# Cookie security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Production uses PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "cb3portfolio_prod"),  # noqa: F405
        "USER": os.getenv("DB_USER"),  # noqa: F405
        "PASSWORD": os.getenv("DB_PASSWORD"),  # noqa: F405
        "HOST": os.getenv("DB_HOST", "localhost"),  # noqa: F405
        "PORT": os.getenv("DB_PORT", "5432"),  # noqa: F405
        "CONN_MAX_AGE": 600,  # Connection pooling
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",  # 30 second query timeout
        },
    }
}

# ============================================================================
# STATIC FILES
# ============================================================================

STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405

# Whitenoise handles compression and caching automatically via STORAGES in base.py
# No additional configuration needed!

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

import os  # noqa: E402

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / "logs"  # noqa: F405
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,  # noqa: F405
            "processor": structlog.processors.JSONRenderer(),  # noqa: F405
            "foreign_pre_chain": [
                structlog.stdlib.add_log_level,  # noqa: F405
                structlog.stdlib.add_logger_name,  # noqa: F405
                structlog.processors.TimeStamper(fmt="iso", utc=True),  # noqa: F405
            ],
        },
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {module}:{lineno} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "file_all": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "application.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "formatter": "json",
        },
        "file_errors": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "errors.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "formatter": "json",
            "level": "ERROR",
        },
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler",
            "level": "ERROR",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file_all"],
        "level": "INFO",
    },
    "loggers": {
        "portfolio": {
            "handlers": ["console", "file_all", "file_errors"],
            "level": "INFO",
            "propagate": False,
        },
        "portfolio.services": {
            "handlers": ["console", "file_all", "file_errors"],
            "level": "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console", "file_all"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file_errors", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "file_errors", "mail_admins"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")  # noqa: F405
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))  # noqa: F405
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"  # noqa: F405
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")  # noqa: F405
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")  # noqa: F405
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@cb3portfolio.com")  # noqa: F405
SERVER_EMAIL = os.getenv("SERVER_EMAIL", "server@cb3portfolio.com")  # noqa: F405

ADMINS = [
    ("Charles Beck III", "charlesbeck@gmail.com"),
]
MANAGERS = ADMINS

# ============================================================================
# PERFORMANCE OPTIMIZATION
# ============================================================================

# Template caching
TEMPLATES[0]["OPTIONS"]["loaders"] = [  # noqa: F405
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

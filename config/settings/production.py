"""
Production settings for cb3portfolio.

SECURITY WARNING: This configuration is for production environments only.
Ensure all environment variables are properly set before deployment.
"""

import os

# Validate production configuration immediately
from config.startup_checks import validate_production_config  # noqa: E402

from .base import *  # noqa: F403

validate_production_config()

# Ensure logs directory exists
LOGS_DIR = BASE_DIR / "logs"  # noqa: F405
LOGS_DIR.mkdir(exist_ok=True)

# ============================================================================
# SECURITY SETTINGS
# ============================================================================

DEBUG = False

# Environment variables validated by startup_checks
SECRET_KEY = os.getenv("SECRET_KEY")  # type: ignore # noqa: F405
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]  # noqa: F405

# HTTPS/SSL Configuration
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Session Security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# CSRF Security
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# Content Security Policy (enforcing mode in production)
CSP_REPORT_ONLY = False


# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "ATOMIC_REQUESTS": True,  # Wrap each view in a transaction
        "CONN_MAX_AGE": 600,  # Connection pooling for 10 minutes
        "CONN_HEALTH_CHECKS": True,  # Django 4.1+ health checks
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}


# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================

# Production: SMTP backend
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@cb3portfolio.com")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", "server@cb3portfolio.com")

# Admins receive error emails (requires EMAIL_HOST to be set)
ADMINS = [("Admin", os.getenv("ADMIN_EMAIL", "admin@cb3portfolio.com"))]
MANAGERS = ADMINS

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
TEMPLATES[0]["APP_DIRS"] = False  # noqa: F405
TEMPLATES[0]["OPTIONS"]["loaders"] = [  # type: ignore # noqa: F405
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    ),
]

# Production: Template string_if_invalid helps catch template errors
TEMPLATES[0]["OPTIONS"]["string_if_invalid"] = "INVALID_TEMPLATE_VAR: %s"  # type: ignore # noqa: F405

# Disable debug toolbar in production
if "debug_toolbar" in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS.remove("debug_toolbar")  # noqa: F405
    MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa: F405

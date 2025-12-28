"""
Django settings for portfolio project.

Base settings shared by all environments.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# Updated for config/settings/base.py (3 levels up)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY") or "django-insecure-placeholder-key-for-tests-and-local-dev"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "False") == "True"

# Configure logging early (before Django uses it)
from config.logging import configure_structlog, get_logging_config  # noqa: E402

configure_structlog(debug=DEBUG)

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS and DEBUG:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "portfolio",
    "users",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "portfolio.middleware.RequestIDMiddleware",  # Add request ID first
    "portfolio.middleware.PerformanceTimingMiddleware",  # Then timing
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "ATOMIC_REQUESTS": True,  # Wrap each view in a transaction
    }
}


# ============================================================================
# PASSWORD VALIDATION
# ============================================================================
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 12,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

# ============================================================================
# STATIC FILES
# ============================================================================

STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Whitenoise Configuration - Compressed static files with caching
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Whitenoise keeps static files cached forever (until hash changes)
WHITENOISE_MAX_AGE = 31536000  # 1 year

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"
LOGIN_URL = "login"

# Custom User Model
AUTH_USER_MODEL = "users.CustomUser"

# ============================================================================
# CONTENT SECURITY POLICY
# ============================================================================

# CSP Configuration (native Django 6.0 support)
CSP_DEFAULT_SRC = ["'self'"]
CSP_SCRIPT_SRC = [
    "'self'",
    "https://cdn.jsdelivr.net",  # Bootstrap JS
]
CSP_STYLE_SRC = [
    "'self'",
    "'unsafe-inline'",  # Required for Bootstrap inline styles
    "https://cdn.jsdelivr.net",  # Bootstrap CSS
]
CSP_FONT_SRC = [
    "'self'",
    "https://cdn.jsdelivr.net",
]
CSP_IMG_SRC = ["'self'", "data:", "https:"]
CSP_CONNECT_SRC = ["'self'"]
CSP_FRAME_ANCESTORS = ["'none'"]  # Prevent clickjacking

# Default to report-only mode (overridden in production)
CSP_REPORT_ONLY = True

# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================

# Development: Console backend (emails printed to console)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@localhost"
SERVER_EMAIL = "server@localhost"

# ============================================================================
# MONITORING CONFIGURATION
# ============================================================================

# Threshold in seconds for logging slow requests
SLOW_REQUEST_THRESHOLD = 1.0

# Logging Configuration
# Using structlog for structured logging with Django's logging system
LOGGING = get_logging_config(debug=DEBUG)

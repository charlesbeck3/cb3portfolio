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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
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

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"
LOGIN_URL = "login"

# Custom User Model
AUTH_USER_MODEL = "users.CustomUser"

# Logging Configuration
# Using structlog for structured logging with Django's logging system
LOGGING = get_logging_config(debug=DEBUG)

# ============================================================================
# CONTENT SECURITY POLICY (Django 6.0 Native)
# ============================================================================

from django.utils.csp import CSP  # noqa: E402

# Development: Report-only mode (logs violations without blocking)
if DEBUG:
    SECURE_CSP_REPORT_ONLY = {
        "default-src": [CSP.SELF],
        "script-src": [
            CSP.SELF,
            CSP.UNSAFE_INLINE,  # Needed for Django forms and Bootstrap components
            "https://cdn.jsdelivr.net",  # Bootstrap JS
        ],
        "style-src": [
            CSP.SELF,
            CSP.UNSAFE_INLINE,  # Needed for inline styles in templates
            "https://cdn.jsdelivr.net",  # Bootstrap CSS
        ],
        "font-src": [
            CSP.SELF,
            "https://cdn.jsdelivr.net",  # Bootstrap Icons
        ],
        "img-src": [
            CSP.SELF,
            "data:",  # For inline images
        ],
        "connect-src": [CSP.SELF],
        "frame-ancestors": [CSP.NONE],  # Prevent clickjacking
        "base-uri": [CSP.SELF],
        "form-action": [CSP.SELF],
    }
else:
    # Production: Enforcing mode (blocks violations)
    SECURE_CSP = {
        "default-src": [CSP.SELF],
        "script-src": [
            CSP.SELF,
            CSP.UNSAFE_INLINE,
            "https://cdn.jsdelivr.net",
        ],
        "style-src": [
            CSP.SELF,
            CSP.UNSAFE_INLINE,
            "https://cdn.jsdelivr.net",
        ],
        "font-src": [
            CSP.SELF,
            "https://cdn.jsdelivr.net",
        ],
        "img-src": [
            CSP.SELF,
            "data:",
        ],
        "connect-src": [CSP.SELF],
        "frame-ancestors": [CSP.NONE],
        "base-uri": [CSP.SELF],
        "form-action": [CSP.SELF],
    }

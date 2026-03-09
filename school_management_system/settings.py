"""
Django settings for school_management_system project.
"""

import os
from pathlib import Path

try:
    from decouple import config
except ImportError:
    def config(key, default=None, cast=None):
        val = os.environ.get(key, default)
        if cast is not None and val is not None:
            if cast is bool:
                return str(val).lower() in ("true", "1", "yes")
            return cast(val)
        return val

import dj_database_url

# -------------------------------
# BASE DIRECTORY
# -------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------------------
# SECURITY
# -------------------------------
SECRET_KEY = config("SECRET_KEY", default="unsafe-secret-key")
DEBUG = config("DEBUG", default=True, cast=bool)

# Add your Render domain here for deployment
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost,schoolmanagementsystem-rr6g.onrender.com"
).split(",")

# -------------------------------
# APPLICATIONS
# -------------------------------
INSTALLED_APPS = [
    # Django Apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Your Apps
    "main_app.apps.MainAppConfig",
]

# -------------------------------
# MIDDLEWARE
# -------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Custom Middleware
    "main_app.middleware.SchoolContextMiddleware",
    "main_app.middleware.LoginCheckMiddleWare",
]

ROOT_URLCONF = "school_management_system.urls"

# -------------------------------
# TEMPLATES
# -------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "main_app" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "main_app.context_processors.notification_context",
            ],
        },
    },
]

WSGI_APPLICATION = "school_management_system.wsgi.application"

# -------------------------------
# DATABASE
# -------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}

# -------------------------------
# AUTHENTICATION
# -------------------------------
AUTH_USER_MODEL = "main_app.CustomUser"
AUTHENTICATION_BACKENDS = ["main_app.EmailBackend.EmailBackend"]

# -------------------------------
# PASSWORD VALIDATION
# -------------------------------
if not DEBUG:
    AUTH_PASSWORD_VALIDATORS = []
else:
    AUTH_PASSWORD_VALIDATORS = [
        {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
        {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
        {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
        {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    ]

# -------------------------------
# INTERNATIONALIZATION
# -------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_L10N = True
USE_TZ = True

# -------------------------------
# STATIC & MEDIA FILES
# -------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "main_app" / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# -------------------------------
# EMAIL CONFIGURATION
# -------------------------------
# Use console backend when no SMTP credentials (development); use SMTP for production
_email_user = config("EMAIL_HOST_USER", default="")
if not _email_user:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = _email_user
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER or "noreply@schoolsystem.com")

# -------------------------------
# CSRF & SESSIONS
# -------------------------------
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Ensure Render domain and localhost are trusted for CSRF
_default_origins = "https://schoolmanagementsystem-rr6g.onrender.com,http://127.0.0.1:8000,http://localhost:8000"
CSRF_TRUSTED_ORIGINS = [x.strip() for x in config("CSRF_TRUSTED_ORIGINS", default=_default_origins).split(",") if x.strip()]

SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = not DEBUG
SESSION_COOKIE_AGE = 172800 if DEBUG else 0
SESSION_COOKIE_SAMESITE = "Lax"

# -------------------------------
# SMS CONFIGURATION
# -------------------------------
SMS_PROVIDER = config("SMS_PROVIDER", default="africas_talking")
AFRICAS_TALKING_API_KEY = config("AFRICAS_TALKING_API_KEY", default="")
AFRICAS_TALKING_USERNAME = config("AFRICAS_TALKING_USERNAME", default="sandbox")
TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = config("TWILIO_AUTH_TOKEN", default="")
TWILIO_PHONE_NUMBER = config("TWILIO_PHONE_NUMBER", default="")
SAFARICOM_CONSUMER_KEY = config("SAFARICOM_CONSUMER_KEY", default="")
SAFARICOM_CONSUMER_SECRET = config("SAFARICOM_CONSUMER_SECRET", default="")
SAFARICOM_SHORTCODE = config("SAFARICOM_SHORTCODE", default="")
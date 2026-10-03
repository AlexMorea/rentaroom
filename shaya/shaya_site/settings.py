"""Settings for the Shaya MVP.

Kept deliberately simple (SQLite, local media) so anyone can run the demo
with two commands. See docs/ARCHITECTURE.md for the production setup.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SHAYA_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("SHAYA_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("SHAYA_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "clips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "shaya_site.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "clips.context_processors.shaya",
            ],
        },
    },
]

WSGI_APPLICATION = "shaya_site.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "shaya.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-za"
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "feed"
LOGOUT_REDIRECT_URL = "feed"

# Uploads: short-form only. 60 MB covers a 3-minute 720p phone clip.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

SHAYA = {
    "MAX_UPLOAD_BYTES": 60 * 1024 * 1024,
    "MAX_DURATION_SECONDS": 180,
    # A view only counts towards earnings once someone has actually watched.
    "QUALIFIED_WATCH_MS": 3000,
    # Same viewer, same video: at most one paid view per this many hours.
    "VIEW_DEDUPE_HOURS": 24,
    # A video starts earning once it has this many lifetime qualified views.
    "MONETISE_THRESHOLD_VIEWS": 1000,
    # Share of net ad revenue that goes to the creator pool (basis points).
    "CREATOR_SHARE_BPS": 5500,
    "MIN_PAYOUT_CENTS": 5000,  # R50 minimum withdrawal
    "AD_EVERY_N_CLIPS": 6,
    # Transcode a ~480p "data saver" copy on upload when ffmpeg is present.
    "TRANSCODE_DATA_SAVER": True,
}

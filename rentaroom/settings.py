from pathlib import Path
import os

try:
    import dj_database_url
except ImportError:
    dj_database_url = None


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-key-change-me")
DEBUG = os.environ.get("DEBUG", "0") == "1"

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
ALLOWED_HOSTS += ["rentaroom-djou.onrender.com"]

extra_hosts = os.environ.get("ALLOWED_HOSTS", "")
if extra_hosts:
    ALLOWED_HOSTS += [h.strip() for h in extra_hosts.split(",") if h.strip()]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cloudinary",
    "cloudinary_storage",
    "listings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rentaroom.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "rentaroom.wsgi.application"


# ================= DATABASE =================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL and dj_database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,  # Render Postgres expects SSL
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }



AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# =======================
# ✅ Cloudinary (Media)
# =======================
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip(),
    "API_KEY": os.environ.get("CLOUDINARY_API_KEY", "").strip(),
    "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", "").strip(),
}

DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

MEDIA_URL = "/media/"  


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/rooms/"
LOGOUT_REDIRECT_URL = "/rooms/"


def env_bool(name, default="False"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()

if BREVO_API_KEY:
    EMAIL_BACKEND = "listings.email_backend.BrevoEmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "thabisomorea@gmail.com").strip()
DEFAULT_FROM_NAME = os.environ.get("DEFAULT_FROM_NAME", "Rooms4You").strip()

BREVO_SANDBOX = env_bool("BREVO_SANDBOX", "0") or env_bool("BREVO_SENDBOX", "0")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": True},
        "rooms4you_email": {"handlers": ["console"], "level": "INFO"},
    },
}

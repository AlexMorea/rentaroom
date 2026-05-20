from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

try:
    import dj_database_url
except ImportError:
    dj_database_url = None


# ================= CORE =================
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-key-change-me")
DEBUG = os.environ.get("DEBUG", "0") == "1"


ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
ALLOWED_HOSTS += [
    ".onrender.com",
    "rooms4you.co.za",
    "www.rooms4you.co.za",
]

extra_hosts = os.environ.get("ALLOWED_HOSTS", "")
if extra_hosts:
    ALLOWED_HOSTS += [h.strip() for h in extra_hosts.split(",") if h.strip()]


CSRF_TRUSTED_ORIGINS = [
    "https://rooms4you.co.za",
    "https://www.rooms4you.co.za",
    "https://*.onrender.com",
]


# ================= APPS =================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    "accounts.apps.AccountsConfig",
    "cloudinary",
    "cloudinary_storage",
    "listings",
    "services",
]


# ================= MIDDLEWARE =================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.MembershipMiddleware",
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

                # GOOGLE MAPS KEY
                "listings.context_processors.google_maps_key",
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
            conn_max_age=60,   # was 600
            ssl_require=True,
        )
    }

    # prevents stale SSL connection failures
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

REDIS_URL = os.getenv("REDIS_URL", "")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            }
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND":
            "django.core.cache.backends.locmem.LocMemCache"
        }
    }

# ================= SECURITY =================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
else:
    SECURE_HSTS_SECONDS = 0

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True


# ================= STATIC / MEDIA =================
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ================= CLOUDINARY =================
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip(),
    "API_KEY": os.environ.get("CLOUDINARY_API_KEY", "").strip(),
    "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", "").strip(),
}

DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"


# ================= AUTH =================
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/rooms/"


# ================= GOOGLE MAPS =================
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


# ================= EMAIL =================
def env_bool(name, default="False"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()

if BREVO_API_KEY:
    EMAIL_BACKEND = "listings.email_backend.BrevoEmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "thabisomorea@gmail.com")
DEFAULT_FROM_NAME = os.environ.get("DEFAULT_FROM_NAME", "Rooms4You")


# ================= LOGGING =================a
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "django.request": {"handlers": ["console"], "level": "ERROR"},
        "rooms4you_email": {"handlers": ["console"], "level": "INFO"},
    },
}

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
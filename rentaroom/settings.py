from pathlib import Path
import os
import re
import secrets
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

try:
    import dj_database_url
except ImportError:
    dj_database_url = None


# ================= CORE =================
# DEBUG should be determined early so we can enforce SECRET_KEY requirements
DEBUG = os.environ.get("DEBUG", "0") == "1"

# Whether flag_overdue_placement_fees actually suspends landlord accounts
# for unpaid Success Fees (14+ days overdue), or just warns and reports
# what it WOULD do. Defaults to False on purpose - this is a real
# consequence for real users and should be a conscious decision, not
# something that ships silently turned on. Flip to True (or set the
# PLACEMENT_FEE_AUTO_SUSPEND=1 env var) once you're ready to enforce it.
PLACEMENT_FEE_AUTO_SUSPEND = os.environ.get("PLACEMENT_FEE_AUTO_SUSPEND", "0") == "1"

# Prefer an explicit SECRET_KEY via env. In development (DEBUG=True) generate
# a strong ephemeral key if none is provided. In production require the env var.
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = secrets.token_urlsafe(50)
        # Persist a single SECRET_KEY line into .env so sessions remain valid
        # across dev server restarts. Replace an existing SECRET_KEY entry if
        # present, otherwise append.
        try:
            env_path = BASE_DIR / ".env"
            env_text = ""
            if env_path.exists():
                env_text = env_path.read_text(encoding="utf-8")

            if re.search(r"^SECRET_KEY=", env_text, flags=re.M):
                new_text = re.sub(r"^SECRET_KEY=.*$", f"SECRET_KEY={SECRET_KEY}", env_text, flags=re.M)
                env_path.write_text(new_text, encoding="utf-8")
            else:
                with open(env_path, "a", encoding="utf-8") as f:
                    if not env_text.endswith("\n") and env_text:
                        f.write("\n")
                    f.write(f"SECRET_KEY={SECRET_KEY}\n")
        except Exception:
            # best-effort only — don't block startup
            pass
    else:
        raise RuntimeError("The SECRET_KEY environment variable must be set in production.")


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
    "django.contrib.sitemaps",

    "accounts.apps.AccountsConfig",
    "cloudinary",
    "cloudinary_storage",
    "listings",
    "services",
    "placements",
    "stays",
]

# Use BigAutoField by default to silence model warnings about AutoField
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


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
    "listings.middleware.DisableCacheMiddleware",
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
SECURE_REFERRER_POLICY = "same-origin"


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


# ================= LOGGING =================
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

# ----------------- Popularity & Scoring Defaults -----------------
# Composite popularity score threshold (rooms with score >= this are "popular").
# Can be overridden with the POPULAR_SCORE_THRESHOLD environment variable.
POPULAR_SCORE_THRESHOLD = int(os.environ.get("POPULAR_SCORE_THRESHOLD", "100"))

# Toggle whether the code should prefer a materialized `Room.score` column
# for ordering and badge decisions. Default enabled but override with env var.
USE_MATERIALIZED_SCORE = env_bool("USE_MATERIALIZED_SCORE", "True")

# ----------------- Celery Defaults -----------------
# Broker URL for Celery (empty by default — Celery disabled until configured).
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "")

# Celery beat schedule dictionary placeholder. Populate in production
# settings or via an environment-specific settings module.
CELERY_BEAT_SCHEDULE = {}

# Default periodic task: compute materialized room scores once per hour.
# Only add the schedule if Celery is installed and `crontab` is available.
try:
    from celery.schedules import crontab

    CELERY_BEAT_SCHEDULE.update({
        "compute-scores-hourly": {
            "task": "listings.tasks.compute_scores_task",
            "schedule": crontab(minute=0, hour="*/1"),
            "args": (False,),
        }
    })
except Exception:
    # Celery not installed in this environment; leave schedule empty.
    pass

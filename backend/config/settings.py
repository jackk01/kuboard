import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit

import redis


BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


LOG_LEVELS = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
    "critical": 50,
    "off": 100,
}


def normalize_log_level(value: Optional[str], default: str = "info") -> str:
    normalized = (value or default).strip().lower()
    return normalized if normalized in LOG_LEVELS else default


def should_emit_log(configured_level: str, target_level: str) -> bool:
    return LOG_LEVELS[configured_level] <= LOG_LEVELS[target_level]


def mask_url(value: str) -> str:
    if not value:
        return value

    parts = urlsplit(value)
    if not parts.netloc or "@" not in parts.netloc:
        return value

    credentials, host = parts.netloc.rsplit("@", 1)
    username, separator, _password = credentials.partition(":")
    masked_credentials = f"{username}:***" if separator else "***"
    return urlunsplit((parts.scheme, f"{masked_credentials}@{host}", parts.path, parts.query, parts.fragment))


def with_redis_password(url: str, password: Optional[str]) -> str:
    if not url or not password:
        return url

    parts = urlsplit(url)
    if not parts.netloc or parts.password is not None:
        return url

    host = parts.netloc.rsplit("@", 1)[-1]
    username = parts.username or ""
    encoded_password = quote(password, safe="")
    credentials = f"{username}:{encoded_password}" if username else f":{encoded_password}"
    return urlunsplit((parts.scheme, f"{credentials}@{host}", parts.path, parts.query, parts.fragment))


def emit_startup_log(level: str, message: str) -> None:
    sys.stderr.write(f"[startup:{level.upper()}] {message}\n")
    sys.stderr.flush()


def probe_database_connection() -> str:
    engine = DATABASES["default"]["ENGINE"]
    name = DATABASES["default"]["NAME"]

    if engine == "django.db.backends.sqlite3":
        try:
            connection = sqlite3.connect(
                name,
                timeout=float(DATABASES["default"].get("OPTIONS", {}).get("timeout", 20)),
            )
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
            finally:
                connection.close()
            return f"ok engine=sqlite3 path={name} query_result={row[0] if row else 'none'}"
        except Exception as exc:  # pragma: no cover - startup diagnostics
            return f"error engine=sqlite3 path={name} reason={exc}"

    return f"skipped unsupported_engine={engine}"


def probe_redis_connection() -> str:
    location = CACHES["default"]["LOCATION"]
    try:
        client = redis.Redis.from_url(location, socket_connect_timeout=2, socket_timeout=2)
        try:
            response = client.ping()
        finally:
            client.close()
        return f"ok location={mask_url(location)} ping={response}"
    except Exception as exc:  # pragma: no cover - startup diagnostics
        return f"error location={mask_url(location)} reason={exc}"

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "kuboard-dev-secret-key-change-me",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "apps.iam.apps.IamConfig",
    "apps.clusters.apps.ClustersConfig",
    "apps.audit.apps.AuditConfig",
    "apps.rbac_bridge.apps.RbacBridgeConfig",
    "apps.streams.apps.StreamsConfig",
    "apps.k8s_gateway.apps.K8SGatewayConfig",
    "apps.system_settings.apps.SystemSettingsConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "common.middleware.RequestIDMiddleware",
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
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "timeout": int(os.getenv("SQLITE_TIMEOUT_SECONDS", "20")),
        },
    }
}

REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_URL = with_redis_password(
    os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
    REDIS_PASSWORD,
)
CELERY_BROKER_URL = with_redis_password(
    os.getenv("CELERY_BROKER_URL", REDIS_URL),
    REDIS_PASSWORD,
)
CELERY_RESULT_BACKEND = with_redis_password(
    os.getenv("CELERY_RESULT_BACKEND", REDIS_URL),
    REDIS_PASSWORD,
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "TIMEOUT": 300,
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_USER_MODEL = "iam.User"

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
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(os.getenv("DJANGO_STATIC_ROOT", str(BASE_DIR / "staticfiles")))
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173",
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

USE_X_FORWARDED_HOST = env_bool("DJANGO_USE_X_FORWARDED_HOST", not DEBUG)
if env_bool("DJANGO_TRUST_X_FORWARDED_PROTO", not DEBUG):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv("DJANGO_SECURE_REFERRER_POLICY", "same-origin")
X_FRAME_OPTIONS = os.getenv("DJANGO_X_FRAME_OPTIONS", "DENY")

CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
KUBOARD_STARTUP_LOG_LEVEL = normalize_log_level(
    os.getenv("KUBOARD_STARTUP_LOG_LEVEL"),
    "info" if DEBUG else "warning",
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": DJANGO_LOG_LEVEL,
    },
}

if should_emit_log(KUBOARD_STARTUP_LOG_LEVEL, "info"):
    emit_startup_log(
        "info",
        (
            "Kuboard settings loaded: "
            f"debug={DEBUG}, "
            f"timezone={TIME_ZONE}, "
            f"django_log_level={DJANGO_LOG_LEVEL}, "
            f"database={DATABASES['default']['ENGINE']}::{DATABASES['default']['NAME']}, "
            f"cache={CACHES['default']['BACKEND']}::{mask_url(CACHES['default']['LOCATION'])}, "
            f"celery_broker={mask_url(CELERY_BROKER_URL)}, "
            f"celery_result_backend={mask_url(CELERY_RESULT_BACKEND)}"
        ),
    )

if should_emit_log(KUBOARD_STARTUP_LOG_LEVEL, "debug"):
    emit_startup_log(
        "debug",
        (
            "Additional startup config: "
            f"allowed_hosts={ALLOWED_HOSTS}, "
            f"cors_allowed_origins={CORS_ALLOWED_ORIGINS}, "
            f"csrf_trusted_origins={CSRF_TRUSTED_ORIGINS}, "
            f"static_root={STATIC_ROOT}, "
            f"session_cookie_secure={SESSION_COOKIE_SECURE}, "
            f"csrf_cookie_secure={CSRF_COOKIE_SECURE}, "
            f"use_x_forwarded_host={USE_X_FORWARDED_HOST}"
        ),
    )
    emit_startup_log("debug", f"database_probe={probe_database_connection()}")
    emit_startup_log("debug", f"redis_probe={probe_redis_connection()}")

#!/bin/sh
set -eu

ROLE="${1:-api}"

export DJANGO_DEBUG="${DJANGO_DEBUG:-false}"
export SQLITE_PATH="${SQLITE_PATH:-/data/db.sqlite3}"

mkdir -p "$(dirname "$SQLITE_PATH")" /app/staticfiles

python manage.py migrate --noinput
python manage.py init_sqlite
python manage.py collectstatic --noinput

if [ "${KUBOARD_BOOTSTRAP_ADMIN:-false}" = "true" ]; then
  python manage.py bootstrap_kuboard \
    --email "${KUBOARD_ADMIN_EMAIL:-admin@kuboard.local}" \
    --password "${KUBOARD_ADMIN_PASSWORD:-admin123456}" \
    --display-name "${KUBOARD_ADMIN_DISPLAY_NAME:-Kuboard Admin}"
fi

if [ "$ROLE" = "api" ]; then
  exec uvicorn config.asgi:application \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${UVICORN_WORKERS:-1}" \
    --proxy-headers
fi

if [ "$ROLE" = "worker" ]; then
  exec celery -A config worker \
    --loglevel "${CELERY_LOG_LEVEL:-INFO}" \
    --concurrency "${CELERY_CONCURRENCY:-1}"
fi

echo "Unknown role: $ROLE" >&2
exit 1


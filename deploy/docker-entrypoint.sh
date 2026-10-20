#!/bin/sh
set -eu

mkdir -p /app/staticfiles /app/media
chown -R www-data:www-data /app/staticfiles /app/media

python manage.py migrate --noinput

# Inicializa somente um banco novo.
if ! python manage.py shell -c "from django.contrib.auth import get_user_model; raise SystemExit(0 if get_user_model().objects.exists() else 1)" >/dev/null 2>&1; then
    python manage.py seed_initial_data
fi

python manage.py collectstatic --noinput
chown -R www-data:www-data /app/staticfiles /app/media

exec gunicorn --workers "${GUNICORN_WORKERS:-2}" --bind 0.0.0.0:8000 --user www-data --group www-data config.wsgi:application

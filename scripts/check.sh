#!/bin/sh
set -eu
export DJANGO_SETTINGS_MODULE=config.test_settings
uv lock --check
uv export --locked --no-dev --no-emit-project --no-header --output-file /tmp/minds-requirements.txt > /dev/null
cmp infra/web/requirements.txt /tmp/minds-requirements.txt
ruff check --no-cache .
python manage.py check --fail-level WARNING
python manage.py migrate --noinput
python manage.py makemigrations --check --dry-run
python manage.py test core --noinput
python manage.py evaluate_ai --check --output /tmp/minds-evaluation.json

#!/usr/bin/env bash
# Render build script - install deps, backup DB, run migrations, collect static files
# MVP SaaS: Updates never delete tenant (school) data. Only schema changes apply.
set -o errexit

pip install -r requirements.txt

# Backup database before migrations (safety - continues if backup fails)
python manage.py backup_db || true

# Apply schema changes only - never recreates or flushes database
python manage.py migrate --no-input

python manage.py collectstatic --no-input

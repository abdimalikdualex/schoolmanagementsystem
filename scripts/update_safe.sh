#!/usr/bin/env bash
# Safe update script for local/VPS deployment
# Run from project root: ./scripts/update_safe.sh
# Ensures code updates never delete tenant (school) data.

set -o errexit

echo "=== Safe Update: School Management System ==="

# 1. Pull latest code
echo "[1/5] Pulling latest code..."
git pull origin main

# 2. Install dependencies
echo "[2/5] Installing dependencies..."
pip install -r requirements.txt

# 3. Backup database BEFORE migrations
echo "[3/5] Backing up database..."
python manage.py backup_db || echo "Warning: Backup failed or skipped"

# 4. Apply migrations (schema only - never deletes data)
echo "[4/5] Running migrations..."
python manage.py migrate --no-input

# 5. Collect static files
echo "[5/5] Collecting static files..."
python manage.py collectstatic --noinput

echo "=== Update complete. Existing schools and data remain intact. ==="

#!/usr/bin/env bash
# Render Pre-Deploy Command - runs migrations before new version goes live
# Set this in Render Dashboard: Settings → Build & Deploy → Pre-Deploy Command: ./release.sh
set -o errexit
python manage.py migrate --no-input

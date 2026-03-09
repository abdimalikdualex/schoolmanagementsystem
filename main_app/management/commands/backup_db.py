"""
Management command to backup the database before migrations.
Prevents data loss during deployment updates.

Run via: python manage.py backup_db

Supports SQLite (file copy) and PostgreSQL (pg_dump).
Backups are stored in backups/ directory with timestamp.
"""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Backup database before migrations (SQLite or PostgreSQL)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-backup',
            action='store_true',
            help='Skip backup (e.g. when backups/ is not writable)'
        )

    def handle(self, *args, **options):
        if options.get('no_backup'):
            self.stdout.write(self.style.WARNING('Skipping backup (--no-backup)'))
            return

        db_settings = settings.DATABASES['default']
        engine = db_settings.get('ENGINE', '')
        backup_dir = Path(settings.BASE_DIR) / 'backups'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        backup_dir.mkdir(parents=True, exist_ok=True)

        if 'sqlite' in engine:
            self._backup_sqlite(db_settings, backup_dir, timestamp)
        elif 'postgresql' in engine:
            self._backup_postgresql(db_settings, backup_dir, timestamp)
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'Backup not implemented for {engine}. '
                    'Consider manual backup before migrate.'
                )
            )

    def _backup_sqlite(self, db_settings, backup_dir, timestamp):
        """Backup SQLite by copying the database file."""
        db_path = db_settings.get('NAME')
        db_path = str(db_path) if db_path else ''
        if not db_path or not os.path.exists(db_path):
            self.stdout.write(
                self.style.WARNING(f'SQLite database not found at {db_path}')
            )
            return

        backup_path = backup_dir / f'db_backup_{timestamp}.sqlite3'
        try:
            shutil.copy2(db_path, backup_path)
            self.stdout.write(
                self.style.SUCCESS(f'Backup created: {backup_path}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Backup failed: {e}')
            )

    def _backup_postgresql(self, db_settings, backup_dir, timestamp):
        """Backup PostgreSQL using pg_dump."""
        backup_path = backup_dir / f'db_backup_{timestamp}.sql'
        try:
            # Use DATABASE_URL if set (e.g. Render, Heroku)
            db_url = os.environ.get('DATABASE_URL')
            if db_url:
                result = subprocess.run(
                    ['pg_dump', db_url, '-f', str(backup_path)],
                    capture_output=True,
                    text=True,
                )
            else:
                # Build connection args from settings
                name = db_settings.get('NAME')
                user = db_settings.get('USER', '')
                password = db_settings.get('PASSWORD', '')
                host = db_settings.get('HOST', 'localhost')
                port = db_settings.get('PORT', '5432')
                env = os.environ.copy()
                if password:
                    env['PGPASSWORD'] = password
                result = subprocess.run(
                    [
                        'pg_dump', '-h', host, '-p', port, '-U', user,
                        '-f', str(backup_path), name
                    ],
                    capture_output=True,
                    text=True,
                    env=env,
                )

            if result.returncode == 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Backup created: {backup_path}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'pg_dump failed (pg_dump may not be installed): '
                        f'{result.stderr or result.stdout}'
                    )
                )
        except FileNotFoundError:
            self.stdout.write(
                self.style.WARNING(
                    'pg_dump not found. Install PostgreSQL client tools. '
                    'Skipping backup.'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Backup failed: {e}')
            )

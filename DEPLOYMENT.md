# Deployment & Safe Update Guide (MVP SaaS)

This document ensures that **code updates from Git never delete existing school data**. The architecture separates code, migrations, and data lifecycle.

## Architecture Principles

| Layer | Purpose | Update Behavior |
|-------|---------|-----------------|
| **Code** | GitHub repository | `git pull` brings new features |
| **Database** | Persistent storage | Never recreated during updates |
| **Migrations** | Schema updates only | Add/modify tables, never drop tenant data |

## Safe Update Process

### Option A: Use the update script (recommended for local/VPS)

```bash
./scripts/update_safe.sh
```

### Option B: Manual steps

When deploying updates from Git, use this flow:

```bash
# 1. Pull latest code
git pull origin main

# 2. Install/update dependencies
pip install -r requirements.txt

# 3. Backup database BEFORE migrations (critical!)
python manage.py backup_db

# 4. Apply schema changes only (never recreates database)
python manage.py migrate --no-input

# 5. Collect static files
python manage.py collectstatic --noinput
```

**Note:** Run `python manage.py makemigrations` only during **local development** when you add new models or fields. Do not run `makemigrations` in production—migration files are committed to Git and applied with `migrate`.

## What This Ensures

- ✅ **Existing schools remain** in the `School` model
- ✅ **All tenant data** (students, teachers, results, fees) stays intact
- ✅ **New features** appear after code update
- ✅ **Schema changes** (new tables, columns) apply via migrations only
- ✅ **No data loss** from code deployments

## Dangerous Commands (Never Use in Production)

These commands **will wipe or reset data**. Do not use them during deployment:

| Command | Risk |
|---------|------|
| `python manage.py flush` | Deletes ALL data in database |
| `python manage.py reset_db` | Drops and recreates database |
| `python manage.py migrate --fake-initial` | Can skip migrations incorrectly |
| `python manage.py loaddata` (without care) | Can overwrite existing data |

## Dangerous Code Patterns (Avoid)

Do not add code that runs on startup or during deployment that:

- `School.objects.all().delete()`
- `call_command('flush')`
- Drops tables or truncates data
- Recreates the database

## Database Backup

### Before Every Update

Always backup before running migrations:

```bash
python manage.py backup_db
```

This creates a timestamped backup in `backups/` (SQLite) or outputs a dump file (PostgreSQL).

### Backup Location

- **SQLite:** `backups/db_backup_YYYYMMDD_HHMMSS.sqlite3`
- **PostgreSQL:** `backups/db_backup_YYYYMMDD_HHMMSS.sql` (requires `pg_dump` in PATH)

### Restore from Backup (SQLite)

```bash
cp backups/db_backup_YYYYMMDD_HHMMSS.sqlite3 db.sqlite3
```

### Restore from Backup (PostgreSQL)

```bash
psql $DATABASE_URL < backups/db_backup_YYYYMMDD_HHMMSS.sql
```

## Render.com Deployment

The `build.sh` script runs automatically on Render:

1. Installs dependencies
2. Backs up database (if possible)
3. Runs migrations (schema updates only)
4. Collects static files

**Render PostgreSQL:** Render provides automatic backups for PostgreSQL. Enable them in the Render dashboard. Our `backup_db` command adds an extra safety layer before migrations.

**Render Ephemeral Disk:** If using SQLite on Render free tier, the disk may not persist between deploys. For production, use Render PostgreSQL add-on for persistent storage.

## Multi-School (Tenant) Isolation

All school-scoped models use a `school` ForeignKey:

- `CustomUser`, `Student`, `Staff`, `Session`, `SchoolClass`, `FeePayment`, etc.
- Updates and migrations **never** drop or truncate these tables
- Each school's data is isolated by `school_id` filters

## Verification After Update

After deploying, verify:

1. **Schools exist:** Log in as Super Admin → Schools list shows registered schools
2. **Users can log in:** School admins can access their dashboard
3. **Data intact:** Students, results, fees visible per school

## Troubleshooting

### "No such table" after update

Run migrations: `python manage.py migrate`

### Migration conflicts

If you have merge conflicts in migration files, resolve them carefully. Never delete migration files that have been applied to production.

### Restore from backup

If something went wrong, restore from the backup created before the update.

---

**Summary:** Updating code from Git applies only code changes and schema migrations. Tenant data (schools, users, students, etc.) is never deleted by the update process.

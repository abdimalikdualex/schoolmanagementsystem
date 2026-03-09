"""
Management command to clear SMS data that has no school association (orphan/legacy data).
Use this to remove test SMS or pre-multi-tenant data so new schools start with clean SMS logs.

Run via: python manage.py clear_orphan_sms
        python manage.py clear_orphan_sms --school SCH001  (clear for specific school)
        python manage.py clear_orphan_sms --dry-run        (preview without deleting)
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from main_app.models import SMSLog, SMSQueue


class Command(BaseCommand):
    help = 'Clear SMS logs and queue items that have no school association (orphan data)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--school',
            type=str,
            help='School code (e.g. SCH001) - clear SMS for this school only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        school_code = options.get('school')
        dry_run = options.get('dry_run', False)

        if school_code:
            # Clear SMS for a specific school
            logs_qs = SMSLog.objects.filter(queue_item__created_by__school__code=school_code)
            queue_qs = SMSQueue.objects.filter(created_by__school__code=school_code)
            scope = f"school {school_code}"
        else:
            # Clear orphan data: no school association (created_by is null or created_by.school is null)
            logs_qs = SMSLog.objects.filter(
                Q(queue_item__isnull=True) | Q(queue_item__created_by__isnull=True) | Q(queue_item__created_by__school__isnull=True)
            )
            queue_qs = SMSQueue.objects.filter(
                Q(created_by__isnull=True) | Q(created_by__school__isnull=True)
            )
            scope = "orphan/legacy (no school association)"

        logs_count = logs_qs.count()
        queue_count = queue_qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would delete {logs_count} SMS logs and {queue_count} queue items ({scope})"
                )
            )
            return

        if logs_count == 0 and queue_count == 0:
            self.stdout.write(self.style.SUCCESS(f"No {scope} SMS data to clear"))
            return

        logs_qs.delete()
        queue_qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {logs_count} SMS logs and {queue_count} queue items ({scope})"
            )
        )

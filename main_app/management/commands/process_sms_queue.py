"""
Management command to process SMS queue
Run via: python manage.py process_sms_queue

Schedule this command to run every 5 minutes using Task Scheduler (Windows) or cron (Linux)
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from main_app.sms_service import process_sms_queue


class Command(BaseCommand):
    help = 'Process pending SMS in the queue and send them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of SMS to process in one batch (default: 50)'
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=3,
            help='Maximum retry attempts for failed SMS (default: 3)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually sending'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        max_retries = options['max_retries']
        dry_run = options['dry_run']

        self.stdout.write(f"Processing SMS queue at {timezone.now()}")
        self.stdout.write(f"Batch size: {batch_size}, Max retries: {max_retries}")

        if dry_run:
            from main_app.models import SMSQueue
            pending = SMSQueue.objects.filter(
                status='pending',
                retry_count__lt=max_retries
            ).count()
            self.stdout.write(self.style.WARNING(f"DRY RUN: Would process {pending} pending SMS"))
            return

        result = process_sms_queue(batch_size=batch_size, max_retries=max_retries)

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed: {result['processed']}, "
                f"Sent: {result['success']}, "
                f"Failed: {result['failed']}"
            )
        )

"""
Management command to send fee reminders to students with outstanding balances
Run via: python manage.py send_fee_reminders

Schedule this command to run daily (e.g., 9:00 AM) using Task Scheduler or cron
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from main_app.models import FeeBalance, FeeStructure, Session, SchoolSettings
from main_app.sms_service import send_fee_reminder_sms, process_sms_queue


class Command(BaseCommand):
    help = 'Send SMS reminders to students/parents with outstanding fee balances'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-balance',
            type=float,
            default=0,
            help='Minimum balance to trigger reminder (default: 0 - any outstanding)'
        )
        parser.add_argument(
            '--days-before-due',
            type=int,
            help='Only send reminders if due date is within X days (default: from settings)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending'
        )

    def handle(self, *args, **options):
        min_balance = options['min_balance']
        days_before_due = options.get('days_before_due')
        dry_run = options['dry_run']

        self.stdout.write(f"Sending fee reminders at {timezone.now()}")

        # Get school settings
        settings = SchoolSettings.objects.first()
        if settings and not settings.enable_fee_reminder_sms:
            self.stdout.write(self.style.WARNING("Fee reminder SMS is disabled in settings"))
            return

        if not days_before_due and settings:
            days_before_due = settings.fee_reminder_days_before

        # Get current session
        session = Session.objects.order_by('-start_year').first()
        if not session:
            self.stdout.write(self.style.ERROR("No active session found"))
            return

        # Get students with outstanding balances
        balances = FeeBalance.objects.filter(
            session=session,
            balance__gt=min_balance
        ).select_related('student__admin', 'fee_structure')

        reminder_count = 0
        skipped_count = 0

        for balance in balances:
            # Use FeeBalance.due_date first, then fee_structure.due_date
            due_date = balance.due_date
            if not due_date and balance.fee_structure:
                due_date = balance.fee_structure.due_date

            # Check if due date is within reminder window (1 week before by default)
            if due_date and days_before_due:
                days_until_due = (due_date - timezone.now().date()).days
                if days_until_due > days_before_due:
                    skipped_count += 1
                    continue

            if dry_run:
                self.stdout.write(
                    f"Would send reminder to {balance.student}: "
                    f"Balance KES {balance.balance:,.2f}"
                )
            else:
                send_fee_reminder_sms(
                    balance.student,
                    balance.balance,
                    due_date
                )
            
            reminder_count += 1

        if not dry_run:
            # Process the SMS queue
            result = process_sms_queue()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued {reminder_count} reminders, "
                    f"Skipped {skipped_count} (not due yet), "
                    f"SMS sent: {result['success']}, failed: {result['failed']}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would queue {reminder_count} reminders, "
                    f"skip {skipped_count}"
                )
            )

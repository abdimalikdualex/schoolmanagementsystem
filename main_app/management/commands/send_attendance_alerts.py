"""
Management command to send attendance alerts to parents of absent students
Run via: python manage.py send_attendance_alerts

Schedule this command to run daily (e.g., 12:00 PM) using Task Scheduler or cron
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from main_app.models import ClassAttendanceRecord, ClassAttendance, SchoolSettings
from main_app.sms_service import send_attendance_alert_sms, process_sms_queue


class Command(BaseCommand):
    help = 'Send SMS alerts to parents of students marked absent today'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Date to check attendance (YYYY-MM-DD format, default: today)'
        )
        parser.add_argument(
            '--resend',
            action='store_true',
            help='Resend alerts even if already sent'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending'
        )

    def handle(self, *args, **options):
        date_str = options.get('date')
        resend = options['resend']
        dry_run = options['dry_run']

        if date_str:
            from datetime import datetime
            check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            check_date = timezone.now().date()

        self.stdout.write(f"Sending attendance alerts for {check_date}")

        # Check settings
        settings = SchoolSettings.objects.first()
        if settings and not settings.enable_attendance_sms:
            self.stdout.write(self.style.WARNING("Attendance SMS is disabled in settings"))
            return

        # Get absent students who haven't been notified (or resend if flag set)
        queryset = ClassAttendanceRecord.objects.filter(
            class_attendance__date=check_date,
            status='absent'
        ).select_related('student__admin', 'class_attendance')

        if not resend:
            queryset = queryset.filter(parent_notified=False)

        absent_records = queryset

        alert_count = 0
        for record in absent_records:
            if dry_run:
                self.stdout.write(
                    f"Would send alert for {record.student} - "
                    f"Absent from {record.class_attendance.school_class}"
                )
            else:
                results = send_attendance_alert_sms(
                    record.student,
                    check_date
                )
                
                if results:
                    record.parent_notified = True
                    record.notification_sent_at = timezone.now()
                    record.save()
            
            alert_count += 1

        if not dry_run:
            # Process the SMS queue
            result = process_sms_queue()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued {alert_count} alerts, "
                    f"SMS sent: {result['success']}, failed: {result['failed']}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Would queue {alert_count} alerts")
            )

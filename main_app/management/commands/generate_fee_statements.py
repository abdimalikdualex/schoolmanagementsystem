"""
Management command to generate monthly fee statements
Run via: python manage.py generate_fee_statements

Schedule this command to run on the 1st of each month
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from main_app.models import Student, FeeBalance, FeePayment, Session
from main_app.sms_service import add_to_sms_queue, process_sms_queue, get_school_settings


class Command(BaseCommand):
    help = 'Generate and optionally send monthly fee statements to parents'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-sms',
            action='store_true',
            help='Send SMS notification about statement availability'
        )
        parser.add_argument(
            '--session',
            type=int,
            help='Session ID (default: current session)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be generated without actually generating'
        )

    def handle(self, *args, **options):
        send_sms = options['send_sms']
        session_id = options.get('session')
        dry_run = options['dry_run']

        self.stdout.write(f"Generating fee statements at {timezone.now()}")

        # Get session
        if session_id:
            session = Session.objects.get(id=session_id)
        else:
            session = Session.objects.order_by('-start_year').first()

        if not session:
            self.stdout.write(self.style.ERROR("No session found"))
            return

        # Get school settings
        school = get_school_settings()

        # Get all students with fee records
        students = Student.objects.filter(
            fee_payments__session=session
        ).distinct().select_related('admin', 'course')

        statement_count = 0
        sms_count = 0

        for student in students:
            # Calculate balance
            payments = FeePayment.objects.filter(
                student=student,
                session=session,
                is_reversed=False
            )
            total_paid = sum(p.amount for p in payments)

            fee_balance, created = FeeBalance.objects.get_or_create(
                student=student,
                session=session,
                defaults={'total_fees': 0}
            )

            if not dry_run:
                fee_balance.total_paid = total_paid
                fee_balance.balance = fee_balance.total_fees - total_paid
                fee_balance.save()

            if dry_run:
                self.stdout.write(
                    f"Would update statement for {student}: "
                    f"Paid: {total_paid}, Balance: {fee_balance.balance}"
                )
            
            statement_count += 1

            # Send SMS notification if enabled
            if send_sms and fee_balance.balance > 0:
                from main_app.models import Parent
                parents = Parent.objects.filter(children=student)
                
                for parent in parents:
                    if parent.admin.phone_number:
                        message = (
                            f"{school.school_name}: Monthly fee statement for "
                            f"{student.admin.first_name}. Total paid: KES {total_paid:,.2f}, "
                            f"Outstanding: KES {fee_balance.balance:,.2f}. "
                            f"Please clear balance to avoid interruption."
                        )
                        
                        if not dry_run:
                            add_to_sms_queue(
                                phone_number=parent.admin.phone_number,
                                message=message,
                                recipient_type='parent',
                                recipient_id=parent.id
                            )
                        sms_count += 1

        if not dry_run and send_sms:
            result = process_sms_queue()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Generated {statement_count} statements, "
                    f"Sent {result['success']} SMS notifications"
                )
            )
        elif dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would generate {statement_count} statements, "
                    f"queue {sms_count} SMS"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Generated {statement_count} statements")
            )

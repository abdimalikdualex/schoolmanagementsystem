"""
Management command to automatically promote students to next grade
Run via: python manage.py auto_promote_students

This should be run manually or at the end of the academic year
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from main_app.models import (
    Course, Session, Student, StudentClassEnrollment, 
    PromotionRecord, GradeLevel
)


class Command(BaseCommand):
    help = 'Automatically promote students from one academic year to the next'

    def add_arguments(self, parser):
        parser.add_argument(
            '--from-session',
            type=int,
            required=True,
            help='Session ID to promote from'
        )
        parser.add_argument(
            '--to-session',
            type=int,
            required=True,
            help='Session ID to promote to'
        )
        parser.add_argument(
            '--from-class',
            type=int,
            help='Specific class ID to promote from (optional, promotes all if not set)'
        )
        parser.add_argument(
            '--to-class',
            type=int,
            help='Specific class ID to promote to (required if --from-class is set)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be promoted without actually promoting'
        )

    def handle(self, *args, **options):
        from_session_id = options['from_session']
        to_session_id = options['to_session']
        from_class_id = options.get('from_class')
        to_class_id = options.get('to_class')
        dry_run = options['dry_run']

        try:
            from_session = Session.objects.get(id=from_session_id)
            to_session = Session.objects.get(id=to_session_id)
        except Session.DoesNotExist:
            self.stdout.write(self.style.ERROR("Invalid session ID"))
            return

        self.stdout.write(
            f"Promoting students from {from_session} to {to_session}"
        )

        if from_class_id:
            # Promote specific class
            if not to_class_id:
                self.stdout.write(self.style.ERROR("--to-class required when --from-class is set"))
                return
            
            try:
                from_class = Course.objects.get(id=from_class_id)
                to_class = Course.objects.get(id=to_class_id)
            except Course.DoesNotExist:
                self.stdout.write(self.style.ERROR("Invalid class ID"))
                return

            classes_to_promote = [(from_class, to_class)]
        else:
            # Auto-determine class promotions based on grade levels
            classes_to_promote = []
            all_classes = Course.objects.filter(is_active=True).select_related('grade_level', 'stream')
            
            for from_class in all_classes:
                if from_class.grade_level:
                    next_grade = from_class.grade_level.get_next_grade()
                    if next_grade:
                        to_class = Course.objects.filter(
                            grade_level=next_grade,
                            stream=from_class.stream,
                            is_active=True
                        ).first()
                        if to_class:
                            classes_to_promote.append((from_class, to_class))

        total_promoted = 0
        total_failed = 0

        for from_class, to_class in classes_to_promote:
            self.stdout.write(f"\nProcessing: {from_class} -> {to_class}")

            # Get active enrollments
            enrollments = StudentClassEnrollment.objects.filter(
                school_class=from_class,
                academic_year=from_session,
                status='active'
            ).select_related('student')

            # Also get students directly assigned
            direct_students = Student.objects.filter(
                course=from_class,
                session=from_session
            )

            students_to_promote = set()
            for enrollment in enrollments:
                students_to_promote.add(enrollment.student)
            for student in direct_students:
                students_to_promote.add(student)

            class_promoted = 0
            class_failed = 0

            if dry_run:
                self.stdout.write(f"  Would promote {len(students_to_promote)} students")
                total_promoted += len(students_to_promote)
                continue

            with transaction.atomic():
                # Create promotion record
                promotion_record = PromotionRecord.objects.create(
                    from_academic_year=from_session,
                    to_academic_year=to_session,
                    from_class=from_class,
                    to_class=to_class,
                    status='processing'
                )

                for student in students_to_promote:
                    try:
                        # Mark old enrollment as completed
                        StudentClassEnrollment.objects.filter(
                            student=student,
                            school_class=from_class,
                            academic_year=from_session
                        ).update(status='completed')

                        # Create new enrollment
                        StudentClassEnrollment.objects.create(
                            student=student,
                            school_class=to_class,
                            academic_year=to_session,
                            status='active'
                        )

                        # Update student's direct assignment
                        student.course = to_class
                        student.session = to_session
                        student.save()

                        class_promoted += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f"  Failed to promote {student}: {e}")
                        )
                        class_failed += 1

                # Update promotion record
                promotion_record.students_promoted = class_promoted
                promotion_record.students_failed = class_failed
                promotion_record.status = 'completed'
                promotion_record.completed_at = timezone.now()
                promotion_record.save()

            self.stdout.write(f"  Promoted: {class_promoted}, Failed: {class_failed}")
            total_promoted += class_promoted
            total_failed += class_failed

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nDRY RUN: Would promote {total_promoted} students total")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nTotal promoted: {total_promoted}, Total failed: {total_failed}"
                )
            )

"""Check which students have a given admission number. Usage: python manage.py check_admission 4545"""
from django.core.management.base import BaseCommand
from main_app.models import Student


class Command(BaseCommand):
    help = 'Check if an admission number is in use and show the student details'

    def add_arguments(self, parser):
        parser.add_argument('admission_number', type=str, help='Admission number to check')

    def handle(self, *args, **options):
        adm = options['admission_number'].strip()
        students = Student.objects.filter(admission_number__iexact=adm).select_related('admin', 'course')
        if not students:
            self.stdout.write(self.style.SUCCESS(f'Admission number "{adm}" is available (not in use).'))
            return
        self.stdout.write(self.style.WARNING(f'Admission number "{adm}" is in use by:'))
        for s in students:
            name = f"{s.admin.first_name} {s.admin.last_name}"
            cls = s.course.name if s.course else 'N/A'
            self.stdout.write(f'  - {name} (ID: {s.id}, Class: {cls})')

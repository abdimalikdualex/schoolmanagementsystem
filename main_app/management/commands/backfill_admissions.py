from django.core.management.base import BaseCommand

from main_app.models import Student, AdmissionSetting


class Command(BaseCommand):
    help = 'Backfill admission numbers for existing students without one'

    def handle(self, *args, **options):
        setting = AdmissionSetting.objects.first()
        if not setting:
            setting = AdmissionSetting.objects.create(next_number=1000)
            self.stdout.write(self.style.SUCCESS(f'Created default AdmissionSetting starting at {setting.next_number}'))

        students = Student.objects.filter(admission_number__isnull=True)
        total = students.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No students require backfill.'))
            return

        assigned = 0
        for s in students:
            s.admission_number = setting.get_next_admission()
            s.save()
            assigned += 1

        self.stdout.write(self.style.SUCCESS(f'Assigned admission numbers to {assigned} students.'))

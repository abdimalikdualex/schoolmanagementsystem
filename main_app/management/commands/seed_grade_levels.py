"""
Management command to seed Kenya CBC Grade Levels

Kenya CBC Structure:
- Pre-Primary: PP1, PP2 (2 years)
- Primary: Grade 1-6 (6 years)
- Junior Secondary: Grade 7-9 (3 years)
- Senior Secondary: Grade 10-12 (3 years)

Usage:
    python manage.py seed_grade_levels
"""

from django.core.management.base import BaseCommand
from main_app.models import GradeLevel


class Command(BaseCommand):
    help = 'Seeds the database with Kenya CBC Grade Levels'

    def handle(self, *args, **options):
        grade_levels = [
            # Pre-Primary (order_index 1-2)
            {
                'code': 'PP1',
                'name': 'Pre-Primary 1',
                'stage': 'preprimary',
                'order_index': 1,
                'description': 'First year of pre-primary education (Age 4-5)'
            },
            {
                'code': 'PP2',
                'name': 'Pre-Primary 2',
                'stage': 'preprimary',
                'order_index': 2,
                'description': 'Second year of pre-primary education (Age 5-6)'
            },
            # Primary (order_index 3-8)
            {
                'code': 'G1',
                'name': 'Grade 1',
                'stage': 'primary',
                'order_index': 3,
                'description': 'First year of primary education (Age 6-7)'
            },
            {
                'code': 'G2',
                'name': 'Grade 2',
                'stage': 'primary',
                'order_index': 4,
                'description': 'Second year of primary education (Age 7-8)'
            },
            {
                'code': 'G3',
                'name': 'Grade 3',
                'stage': 'primary',
                'order_index': 5,
                'description': 'Third year of primary education (Age 8-9)'
            },
            {
                'code': 'G4',
                'name': 'Grade 4',
                'stage': 'primary',
                'order_index': 6,
                'description': 'Fourth year of primary education (Age 9-10)'
            },
            {
                'code': 'G5',
                'name': 'Grade 5',
                'stage': 'primary',
                'order_index': 7,
                'description': 'Fifth year of primary education (Age 10-11)'
            },
            {
                'code': 'G6',
                'name': 'Grade 6',
                'stage': 'primary',
                'order_index': 8,
                'description': 'Sixth year of primary education (Age 11-12)'
            },
            # Junior Secondary (order_index 9-11)
            {
                'code': 'G7',
                'name': 'Grade 7',
                'stage': 'junior_secondary',
                'order_index': 9,
                'description': 'First year of junior secondary education (Age 12-13)'
            },
            {
                'code': 'G8',
                'name': 'Grade 8',
                'stage': 'junior_secondary',
                'order_index': 10,
                'description': 'Second year of junior secondary education (Age 13-14)'
            },
            {
                'code': 'G9',
                'name': 'Grade 9',
                'stage': 'junior_secondary',
                'order_index': 11,
                'description': 'Third year of junior secondary education (Age 14-15)'
            },
            # Senior Secondary (order_index 12-14) - Optional
            {
                'code': 'G10',
                'name': 'Grade 10',
                'stage': 'senior_secondary',
                'order_index': 12,
                'description': 'First year of senior secondary education (Age 15-16)'
            },
            {
                'code': 'G11',
                'name': 'Grade 11',
                'stage': 'senior_secondary',
                'order_index': 13,
                'description': 'Second year of senior secondary education (Age 16-17)'
            },
            {
                'code': 'G12',
                'name': 'Grade 12',
                'stage': 'senior_secondary',
                'order_index': 14,
                'description': 'Third year of senior secondary education (Age 17-18)'
            },
        ]

        created_count = 0
        updated_count = 0

        for level_data in grade_levels:
            obj, created = GradeLevel.objects.update_or_create(
                code=level_data['code'],
                defaults=level_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created: {level_data["code"]} - {level_data["name"]}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated: {level_data["code"]} - {level_data["name"]}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nCompleted! Created: {created_count}, Updated: {updated_count}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                '\nKenya CBC Grade Levels seeded successfully!'
            )
        )

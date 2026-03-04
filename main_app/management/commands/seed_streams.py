"""
Management command to seed default streams (class sections)

Usage:
    python manage.py seed_streams
"""

from django.core.management.base import BaseCommand
from main_app.models import Stream


class Command(BaseCommand):
    help = 'Seeds the database with default class streams'

    def handle(self, *args, **options):
        streams = [
            {'name': 'East', 'code': 'E'},
            {'name': 'West', 'code': 'W'},
            {'name': 'North', 'code': 'N'},
            {'name': 'South', 'code': 'S'},
            {'name': 'Blue', 'code': 'B'},
            {'name': 'Red', 'code': 'R'},
            {'name': 'Green', 'code': 'G'},
            {'name': 'Yellow', 'code': 'Y'},
        ]

        created_count = 0
        
        for stream_data in streams:
            obj, created = Stream.objects.get_or_create(
                name=stream_data['name'],
                defaults=stream_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created stream: {stream_data["name"]}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Stream already exists: {stream_data["name"]}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nCompleted! Created: {created_count} streams')
        )

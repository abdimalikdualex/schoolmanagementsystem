"""
Management command to create a default admin user for login testing.

Usage:
    python manage.py create_admin

Creates: admin@school.com / admin123 (or updates password if user exists)
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Creates a default admin user (admin@school.com / admin123) for testing'

    def handle(self, *args, **options):
        User = get_user_model()
        email = 'admin@school.com'
        password = 'admin123'

        try:
            user = User.objects.get(email__iexact=email)
            created = False
        except User.DoesNotExist:
            user = User(
                email=email,
                first_name='Admin',
                last_name='User',
                gender='M',
                address='School Management',
                user_type='1',
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            created = True

        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(
                f'Admin user created: {email} / {password}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Admin password updated: {email} / {password}'
            ))
        self.stdout.write('You can now login with these credentials.')

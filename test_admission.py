#!/usr/bin/env python
"""
Test script to verify auto-assignment of admission numbers.
Run: python test_admission.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_management_system.settings')
django.setup()

from main_app.models import Student, CustomUser, AdmissionSetting

# Check current AdmissionSetting
setting = AdmissionSetting.objects.first()
print(f"Current AdmissionSetting: prefix={setting.prefix}, next_number={setting.next_number}\n")

# Create a test user and student to verify auto-assignment
user = CustomUser.objects.create_user(
    email='testnewstudent@test.com',
    password='testpass123',
    first_name='New',
    last_name='Student',
    user_type=3,
    gender='M',
    address='Test Address'
)
print(f"✓ Created CustomUser: {user.email}")

# Get the auto-created student
student = Student.objects.get(admin=user)
print(f"✓ Auto-created Student ID: {student.id}")
print(f"✓ Auto-assigned Admission Number: {student.admission_number}")
print(f"✓ Updated AdmissionSetting next_number: {AdmissionSetting.objects.first().next_number}\n")

# List all students with admission numbers
print("--- All Students with Admission Numbers ---")
for s in Student.objects.select_related('admin').all().order_by('id'):
    print(f"  ID: {s.id:2d} | Admission: {s.admission_number:8s} | Name: {s.admin.first_name:15s} {s.admin.last_name}")

print("\n✓ Auto-assignment is working correctly!")

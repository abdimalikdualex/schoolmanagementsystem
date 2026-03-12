"""
Safe update utilities for multi-tenant school management.
Prevents data loss and cross-school corruption during updates.
"""
from django.db import transaction


def get_school_from_request(request):
    """Get current school from request (set by middleware)."""
    return getattr(request, 'school', None)


def validate_course_belongs_to_school(course, school):
    """
    Validate that a course/class belongs to the given school.
    Returns (True, None) if valid, (False, error_message) if invalid.
    """
    if not school:
        return True, None
    if not course:
        return False, "Class is required."
    if hasattr(course, 'school_id') and course.school_id and course.school_id != school.id:
        return False, "Selected class does not belong to your school."
    return True, None


def validate_staff_belongs_to_school(staff, school):
    """Validate staff belongs to school."""
    if not school:
        return True, None
    if not staff:
        return False, "Staff is required."
    if hasattr(staff, 'admin') and staff.admin and hasattr(staff.admin, 'school_id'):
        if staff.admin.school_id and staff.admin.school_id != school.id:
            return False, "Selected staff does not belong to your school."
    return True, None


def validate_student_belongs_to_school(student, school):
    """Validate student belongs to school."""
    if not school:
        return True, None
    if not student:
        return False, "Student is required."
    if hasattr(student, 'admin') and student.admin and hasattr(student.admin, 'school_id'):
        if student.admin.school_id and student.admin.school_id != school.id:
            return False, "Student does not belong to your school."
    return True, None


def validate_subject_belongs_to_school(subject, school):
    """Validate subject's course belongs to school."""
    if not school:
        return True, None
    if not subject or not subject.course_id:
        return False, "Subject or class is required."
    if hasattr(subject.course, 'school_id') and subject.course.school_id and subject.course.school_id != school.id:
        return False, "Subject's class does not belong to your school."
    return True, None


def safe_update_student(student, school, **updates):
    """
    Update student fields safely. Only updates provided fields.
    Use within transaction.atomic().
    """
    for key, value in updates.items():
        if hasattr(student, key):
            setattr(student, key, value)
    student.save()
    return student


def safe_update_course(course, school, **updates):
    """Update course/class fields safely."""
    for key, value in updates.items():
        if hasattr(course, key):
            setattr(course, key, value)
    course.save()
    return course

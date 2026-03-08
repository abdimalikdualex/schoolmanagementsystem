from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import UserManager
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db import models
from django.contrib.auth.models import AbstractUser




class CustomUserManager(UserManager):
    def _create_user(self, email, password, **extra_fields):
        email = self.normalize_email(email)
        user = CustomUser(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("first_name", "Admin")
        extra_fields.setdefault("last_name", "User")
        extra_fields.setdefault("gender", "M")
        extra_fields.setdefault("address", "N/A")

        assert extra_fields["is_staff"]
        assert extra_fields["is_superuser"]
        return self._create_user(email, password, **extra_fields)


# ============================================
# MULTI-TENANT: SUBSCRIPTION & SCHOOL MODELS
# ============================================

class SubscriptionPlan(models.Model):
    """
    Subscription plans for schools. Owner assigns plans and enforces limits.
    """
    name = models.CharField(max_length=50, unique=True)  # Starter, Standard, Premium
    student_limit = models.PositiveIntegerField(default=100, help_text="Max students allowed")
    teacher_limit = models.PositiveIntegerField(default=20, help_text="Max teachers allowed")
    monthly_price = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="Monthly price (e.g. 15.00)")
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['student_limit']
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"

    def __str__(self):
        return self.name


class School(models.Model):
    """
    Represents a tenant institution in the multi-school platform.
    All school-scoped data is isolated by school_id.
    Schools must be approved by Platform Owner before they can access the system.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True, help_text="Unique code e.g., SCH001, used for subdomain")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='schools/', blank=True, null=True)
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schools',
        help_text="Plan controls student/teacher limits"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Only approved schools can access the system"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.name

    def get_student_count(self):
        from django.apps import apps
        Student = apps.get_model('main_app', 'Student')
        return Student.objects.filter(admin__school=self).count()

    def get_teacher_count(self):
        from django.apps import apps
        Staff = apps.get_model('main_app', 'Staff')
        return Staff.objects.filter(admin__school=self).count()

    def can_add_student(self):
        """Check if school can add more students based on plan limit. 0 = unlimited."""
        if not self.subscription_plan:
            return True
        limit = self.subscription_plan.student_limit
        if limit == 0:
            return True  # Unlimited
        return self.get_student_count() < limit

    def can_add_teacher(self):
        """Check if school can add more teachers based on plan limit. 0 = unlimited."""
        if not self.subscription_plan:
            return True
        limit = self.subscription_plan.teacher_limit
        if limit == 0:
            return True  # Unlimited
        return self.get_teacher_count() < limit


class SchoolSubscription(models.Model):
    """Track school subscription with start/end dates and payment status."""
    PAYMENT_STATUS = (
        ('paid', 'Paid'),
        ('pending', 'Pending'),
        ('expired', 'Expired'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='school_subscriptions')
    start_date = models.DateField()
    end_date = models.DateField()
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "School Subscription"
        verbose_name_plural = "School Subscriptions"

    def __str__(self):
        return f"{self.school.name} - {self.plan.name} ({self.start_date} to {self.end_date})"

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.end_date < timezone.now().date()


class Session(models.Model):
    """
    Academic session (year + term). Used for enrollment, attendance, and grading.
    Each session belongs to a school for multi-tenant isolation.
    """
    TERM_CHOICES = [
        ('term1', 'Term I (January-April)'),
        ('term2', 'Term II (May-August)'),
        ('term3', 'Term III (September-December)'),
    ]
    TERM_DATE_RANGES = {
        'term1': ((1, 1), (4, 30)),   # Jan 1 - Apr 30
        'term2': ((5, 1), (8, 31)),   # May 1 - Aug 31
        'term3': ((9, 1), (12, 31)),  # Sep 1 - Dec 31
    }
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sessions',
        help_text="Null for legacy data; required for multi-tenant"
    )
    academic_year = models.IntegerField(help_text="e.g., 2026", default=2026)
    term = models.CharField(max_length=10, choices=TERM_CHOICES, default='term1')
    start_year = models.DateField()  # Computed from academic_year + term
    end_year = models.DateField()    # Computed from academic_year + term

    class Meta:
        ordering = ['-academic_year', 'term']

    def save(self, *args, **kwargs):
        from datetime import date
        if self.academic_year and self.term:
            start_m, start_d = self.TERM_DATE_RANGES[self.term][0]
            end_m, end_d = self.TERM_DATE_RANGES[self.term][1]
            self.start_year = date(self.academic_year, start_m, start_d)
            self.end_year = date(self.academic_year, end_m, end_d)
        super().save(*args, **kwargs)

    def __str__(self):
        term_label = dict(self.TERM_CHOICES).get(self.term, self.term)
        return f"{self.academic_year} - {term_label}"


class AcademicTerm(models.Model):
    """
    Academic Term - controls enrollment, subjects, attendance, and grading.
    Only ONE active term per school at any time.
    Kenyan structure: Term 1, Term 2, Term 3 per academic year.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Closed'),
    ]
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='academic_terms',
        help_text="Null for legacy data; required for multi-tenant"
    )
    academic_year = models.IntegerField(help_text="e.g., 2025")
    term_name = models.CharField(max_length=50, help_text="e.g., Term 1, Term 2, Term 3")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='closed')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year', 'term_name']
        unique_together = ['academic_year', 'term_name']
        verbose_name = "Academic Term"
        verbose_name_plural = "Academic Terms"

    def __str__(self):
        return f"{self.academic_year} - {self.term_name} ({self.get_status_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError({'end_date': 'End date must be after start date.'})
        # Check overlap with other terms in same year AND same school (multi-tenant)
        overlap_qs = AcademicTerm.objects.filter(
            academic_year=self.academic_year
        ).filter(
            models.Q(start_date__lte=self.end_date, end_date__gte=self.start_date)
        )
        if self.school_id:
            overlap_qs = overlap_qs.filter(school=self.school)
        else:
            overlap_qs = overlap_qs.filter(school__isnull=True)
        if self.pk:
            overlap_qs = overlap_qs.exclude(pk=self.pk)
        if overlap_qs.exists():
            raise ValidationError(
                'Term dates overlap with another term in the same academic year.'
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.status == 'active':
            # Only one active term per school: close others in same school
            qs = AcademicTerm.objects.exclude(pk=self.pk)
            if self.school_id:
                qs = qs.filter(school=self.school)
            qs.update(status='closed')
        super().save(*args, **kwargs)

    @classmethod
    def get_active_term(cls, school=None):
        """Returns the single active term for the school, or None. If school is None, returns first active (legacy)."""
        qs = cls.objects.filter(status='active')
        if school is not None:
            qs = qs.filter(school=school)
        return qs.first()

    def activate(self):
        """Set this term as active; close all others."""
        AcademicTerm.objects.exclude(pk=self.pk).update(status='closed')
        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])

    def close(self):
        """Close this term - locks attendance and marks editing."""
        self.status = 'closed'
        self.save(update_fields=['status', 'updated_at'])

    @property
    def is_locked(self):
        """When closed, attendance and marks cannot be edited."""
        return self.status == 'closed'


class GradeLevel(models.Model):
    """Kenya Grade Levels - CBC (Grade 1–6, Junior/Senior Secondary) or 8-4-4 (Form 1–4)"""
    STAGE_CHOICES = [
        ('preprimary', 'Pre-Primary'),
        ('primary', 'Primary'),
        ('junior_secondary', 'Junior Secondary'),
        ('senior_secondary', 'Senior Secondary'),
        ('form', 'Form (8-4-4)'),  # Form 1–4
    ]
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='grade_levels',
        help_text="Null for legacy data; required for multi-tenant"
    )
    code = models.CharField(max_length=10, help_text="e.g., PP1, G1-G6, F1-F4")
    name = models.CharField(max_length=50, help_text="e.g., Grade 1, Form 1")
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    order_index = models.PositiveIntegerField(help_text="For promotion sequence")
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_next_grade(self, school=None):
        """Get the next grade level for promotion"""
        qs = GradeLevel.objects.filter(
            order_index=self.order_index + 1,
            is_active=True
        )
        if school is not None:
            qs = qs.filter(school=school)
        elif self.school_id:
            qs = qs.filter(school=self.school)
        return qs.first()

    class Meta:
        ordering = ['order_index']
        verbose_name = "Grade Level"
        verbose_name_plural = "Grade Levels"


class CustomUser(AbstractUser):
    USER_TYPE = (
        (0, "Super Admin"),  # Platform owner - no school, manages all schools
        (1, "HOD"),          # School Admin
        (2, "Staff"),        # Teacher
        (3, "Student"),
        (4, "Parent"),
        (5, "Finance Officer"),
    )
    GENDER = [("M", "Male"), ("F", "Female")]

    username = None  # Removed username, using email instead
    email = models.EmailField(unique=True)
    user_type = models.CharField(default=1, choices=USER_TYPE, max_length=1)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
        help_text="Null for Super Admin; required for all other roles"
    )
    gender = models.CharField(max_length=1, choices=GENDER)
    profile_pic = models.ImageField(blank=True, null=True)
    address = models.TextField()
    phone_number = models.CharField(max_length=15, blank=True, null=True, help_text="Phone number in format: 254712345678")
    fcm_token = models.TextField(default="")  # For firebase notifications
    email_verified = models.BooleanField(default=True, help_text="False for new school admins until they verify")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = CustomUserManager()

    def __str__(self):
        return self.last_name + ", " + self.first_name


class EmailVerification(models.Model):
    """Token for verifying school admin email during registration."""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='email_verifications')
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Email Verification"
        verbose_name_plural = "Email Verifications"


class Admin(models.Model):
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)


class Stream(models.Model):
    """Class streams (e.g., East, West, Blue, North)"""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='streams',
        help_text="Null for legacy data; required for multi-tenant"
    )
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=10, blank=True, null=True, help_text="Short code e.g., E, W, B")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


# Keep Section as alias for backward compatibility
Section = Stream


class SchoolClass(models.Model):
    """
    Class entity - represents a group of learners in a grade and stream.
    Kenyan structure: CBC (Grade 1–6, Junior Secondary, Senior Secondary) or 8-4-4 (Form 1–4).
    """
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='classes',
        help_text="Null for legacy data; required for multi-tenant"
    )
    name = models.CharField(max_length=120, help_text="e.g., Grade 4 East, Form 2 Blue")
    grade_level = models.ForeignKey(
        GradeLevel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='classes'
    )
    stream = models.ForeignKey(
        Stream, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='classes'
    )
    # Keep section for backward compatibility
    section = models.ForeignKey(
        Stream, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='school_classes_legacy'
    )
    academic_year = models.ForeignKey(
        Session,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='classes'
    )
    class_teacher = models.ForeignKey(
        'Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_classes'
    )
    capacity = models.PositiveIntegerField(default=40, help_text="Maximum number of students")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.grade_level and self.stream:
            return f"{self.grade_level.code} {self.stream.name}"
        elif self.stream:
            return f"{self.name} - {self.stream.name}"
        return self.name

    @property
    def current_enrollment_count(self):
        """Get current number of enrolled students"""
        return self.enrollments.filter(status='active').count()
    
    @property
    def available_slots(self):
        """Get available slots in class"""
        return max(0, self.capacity - self.current_enrollment_count)

    class Meta:
        db_table = 'main_app_course'  # Legacy table name
        ordering = ['grade_level__order_index', 'stream__name', 'name']
        verbose_name = "Class"
        verbose_name_plural = "Classes"


# Backward compatibility alias (Course was renamed to SchoolClass)
Course = SchoolClass


class AdmissionSetting(models.Model):
    """Stores admission numbering configuration."""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='admission_settings',
        help_text="Null for legacy data; one per school for multi-tenant"
    )
    prefix = models.CharField(max_length=10, default='ADM')
    start_number = models.PositiveIntegerField(default=1000)
    next_number = models.PositiveIntegerField(default=1000)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prefix}-{self.next_number}"

    def get_next_admission(self):
        adm = f"{self.prefix}{self.next_number}"
        self.next_number += 1
        self.save()
        return adm

class Student(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('transferred', 'Transferred'),
        ('withdrawn', 'Withdrawn'),
        ('suspended', 'Suspended'),
    ]
    
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.DO_NOTHING, null=True)
    admission_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    current_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_students'
    )
    # Backward compatibility: course field (legacy, sync with current_class)
    course = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students_legacy',
        db_column='course_id'
    )
    # New fields matching the screenshot
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    admission_date = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    # Fee tracking
    total_fee_billed = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return self.admin.last_name + ", " + self.admin.first_name
    
    def get_current_enrollment(self):
        """Get the student's current active enrollment"""
        return self.enrollments.filter(status='active').first()
    
    def get_class_info(self):
        """Get current class information"""
        enrollment = self.get_current_enrollment()
        if enrollment:
            return enrollment.school_class
        return self.current_class
    
    def get_guardians(self):
        """Get all guardians for this student"""
        return self.guardians.all()
    
    def get_total_paid(self):
        """Get total amount paid by student"""
        from django.db.models import Sum
        total = self.student_fee_payments.filter(is_reversed=False).aggregate(total=Sum('amount'))
        return total['total'] or 0
    
    def get_fee_balance(self):
        """Get outstanding fee balance"""
        return self.total_fee_billed - self.get_total_paid()


class Staff(models.Model):
    course = models.ForeignKey(Course, on_delete=models.DO_NOTHING, null=True, blank=True, verbose_name="Class")
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return self.admin.last_name + " " + self.admin.first_name
    
    def get_assigned_classes(self):
        """Get all classes where this staff is the class teacher"""
        return Course.objects.filter(class_teacher=self, is_active=True)
    
    def get_teaching_classes(self):
        """Get all classes where this staff teaches subjects"""
        return Course.objects.filter(
            subject__staff=self
        ).distinct()


class StudentClassEnrollment(models.Model):
    """Tracks student placement per academic year - supports promotion and historical records"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('transferred', 'Transferred'),
        ('completed', 'Completed'),
        ('promoted', 'Promoted'),
        ('withdrawn', 'Withdrawn'),
        ('repeated', 'Repeated'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    school_class = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    academic_year = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='enrollments')
    term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='enrollments', help_text="Academic term for this enrollment"
    )
    admission_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    previous_enrollment = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='next_enrollment',
        help_text="Link to previous year's enrollment for tracking history"
    )
    promoted_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promoted_to'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.school_class} ({self.academic_year})"

    class Meta:
        ordering = ['-academic_year__start_year', 'student__admin__last_name']
        unique_together = ['student', 'academic_year']
        verbose_name = "Student Enrollment"
        verbose_name_plural = "Student Enrollments"


class StudentSubjectEnrollment(models.Model):
    """MVP: Auto-created when student enrolled - links student to subjects for Class+Stream+Term"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='subject_enrollments')
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='student_enrollments')
    term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='subject_enrollments'
    )
    enrollment = models.ForeignKey(
        StudentClassEnrollment, on_delete=models.CASCADE, null=True, blank=True,
        related_name='subject_enrollments'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'subject', 'term']
        verbose_name = "Student Subject Enrollment"
        verbose_name_plural = "Student Subject Enrollments"


class ContinuousAssessment(models.Model):
    """MVP: CATs - Continuous Assessment Tests (e.g., CAT 1, CAT 2)"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='cat_marks')
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='cat_marks')
    term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='cat_marks'
    )
    assessment_name = models.CharField(max_length=100, help_text="e.g., CAT 1, CAT 2, Assignment 1")
    marks = models.FloatField()
    max_marks = models.FloatField(default=100)
    entered_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Continuous Assessment"
        verbose_name_plural = "Continuous Assessments"


class SubjectAttendance(models.Model):
    """MVP: Attendance per Student + Subject + Term + Date"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='subject_attendances')
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='attendances')
    term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='subject_attendances'
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=[
        ('present', 'Present'), ('absent', 'Absent'), ('late', 'Late'),
        ('excused', 'Excused'), ('half_day', 'Half Day'),
    ], default='present')
    marked_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'subject', 'date']
        ordering = ['-date']
        verbose_name = "Subject Attendance"
        verbose_name_plural = "Subject Attendances"


class Parent(models.Model):
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    children = models.ManyToManyField('Student', related_name='parents', blank=True)
    occupation = models.CharField(max_length=100, blank=True, null=True)
    relationship = models.CharField(max_length=50, default='Parent', help_text="e.g., Father, Mother, Guardian")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.admin.last_name} {self.admin.first_name}"

    class Meta:
        verbose_name = "Parent/Guardian"
        verbose_name_plural = "Parents/Guardians"


class Guardian(models.Model):
    """
    Simple Guardian model - doesn't require a user account.
    Stores guardian name and phone number for SMS notifications.
    Matches the screenshot design for "Guardians/Parents" section.
    """
    RELATIONSHIP_CHOICES = [
        ('father', 'Father'),
        ('mother', 'Mother'),
        ('guardian', 'Guardian'),
        ('uncle', 'Uncle'),
        ('aunt', 'Aunt'),
        ('grandparent', 'Grandparent'),
        ('sibling', 'Sibling'),
        ('other', 'Other'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='guardians')
    name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, default='guardian')
    is_primary = models.BooleanField(default=False, help_text="Primary contact for SMS")
    occupation = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_relationship_display()}) - {self.phone_number}"

    class Meta:
        ordering = ['-is_primary', 'name']
        verbose_name = "Guardian"
        verbose_name_plural = "Guardians"


class Subject(models.Model):
    name = models.CharField(max_length=120)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE,
        verbose_name="Class"
    )
    term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='subjects', help_text="Term this subject is offered"
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Attendance(models.Model):
    session = models.ForeignKey(Session, on_delete=models.DO_NOTHING)
    subject = models.ForeignKey(Subject, on_delete=models.DO_NOTHING)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AttendanceReport(models.Model):
    student = models.ForeignKey(Student, on_delete=models.DO_NOTHING)
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE)
    status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeaveReportStudent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date = models.CharField(max_length=60)
    message = models.TextField()
    status = models.SmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeaveReportStaff(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    date = models.CharField(max_length=60)
    message = models.TextField()
    status = models.SmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FeedbackStudent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    feedback = models.TextField()
    reply = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FeedbackStaff(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    feedback = models.TextField()
    reply = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationStaff(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationStudent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class StudentResult(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    test = models.FloatField(default=0)
    exam = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class StudentFees(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partial', 'Partial Payment'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fees')
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    due_date = models.DateField()
    payment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.student.admin.last_name} - {self.session} - {self.status.upper()}"
    
    @property
    def amount_outstanding(self):
        return self.amount_due - self.amount_paid
    
    class Meta:
        unique_together = ('student', 'session')


class AdminPermission(models.Model):
    PERMISSION_CHOICES = [
        ('view_fees', 'View Fees'),
        ('manage_fees', 'Manage Fees'),
        ('edit_results', 'Edit Results'),
        ('view_results', 'View Results'),
        ('manage_students', 'Manage Students'),
        ('manage_staff', 'Manage Staff'),
    ]
    
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='admin_permissions')
    can_view_fees = models.BooleanField(default=False)
    can_manage_fees = models.BooleanField(default=False)
    can_edit_results = models.BooleanField(default=False)
    can_view_results = models.BooleanField(default=True)
    can_manage_students = models.BooleanField(default=False)
    can_manage_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.admin.username} - Permissions"
    
    class Meta:
        verbose_name = "Admin Permission"
        verbose_name_plural = "Admin Permissions"


class PromotionRecord(models.Model):
    """Track bulk promotion operations"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    from_academic_year = models.ForeignKey(
        Session, 
        on_delete=models.CASCADE, 
        related_name='promotions_from'
    )
    to_academic_year = models.ForeignKey(
        Session, 
        on_delete=models.CASCADE, 
        related_name='promotions_to'
    )
    from_class = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='promotions_from',
        null=True,
        blank=True,
        help_text="Source class (optional - if null, promotes all classes)"
    )
    to_class = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='promotions_to',
        null=True,
        blank=True,
        help_text="Target class for promoted students"
    )
    students_promoted = models.PositiveIntegerField(default=0)
    students_repeated = models.PositiveIntegerField(default=0)
    students_failed = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    promoted_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Promotion: {self.from_academic_year} → {self.to_academic_year}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Promotion Record"
        verbose_name_plural = "Promotion Records"


@receiver(post_save, sender=CustomUser)
def create_admin_permissions(sender, instance, created, **kwargs):
    """Create AdminPermission when new admin user is created"""
    if created and instance.user_type == 1:
        AdminPermission.objects.create(admin=instance)


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == '1':
            Admin.objects.create(admin=instance)
        if instance.user_type == '2':
            Staff.objects.create(admin=instance)
        if instance.user_type == '3':
            Student.objects.create(admin=instance)
        if instance.user_type == '4':
            Parent.objects.create(admin=instance)


@receiver(post_save, sender=CustomUser)
def save_user_profile(sender, instance, **kwargs):
    if instance.user_type == '1' and hasattr(instance, 'admin'):
        instance.admin.save()
    if instance.user_type == '2' and hasattr(instance, 'staff'):
        instance.staff.save()
    if instance.user_type == '3' and hasattr(instance, 'student'):
        instance.student.save()
    if instance.user_type == '4' and hasattr(instance, 'parent'):
        instance.parent.save()


class Timetable(models.Model):
    DAYS_OF_WEEK = [
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ]
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='timetables', verbose_name="Class")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    day = models.CharField(max_length=10, choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True, null=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.course.name} - {self.subject.name} ({self.day})"

    class Meta:
        ordering = ['day', 'start_time']
        unique_together = ['course', 'day', 'start_time', 'session']


class Homework(models.Model):
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
    ]
    
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='homework')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name="Class")
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    due_date = models.DateTimeField()
    attachment = models.FileField(upload_to='homework/', blank=True, null=True)
    max_marks = models.IntegerField(default=100)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.subject.name}"

    class Meta:
        ordering = ['-due_date']
        verbose_name_plural = "Homework"


class HomeworkSubmission(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    submission_file = models.FileField(upload_to='homework_submissions/', blank=True, null=True)
    submission_text = models.TextField(blank=True, null=True)
    marks_obtained = models.IntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student} - {self.homework.title}"

    class Meta:
        unique_together = ['homework', 'student']


class Announcement(models.Model):
    TARGET_CHOICES = [
        ('all', 'All Users'),
        ('students', 'Students Only'),
        ('staff', 'Staff Only'),
        ('parents', 'Parents Only'),
        ('class', 'Specific Class'),
    ]
    
    title = models.CharField(max_length=200)
    content = models.TextField()
    target_audience = models.CharField(max_length=20, choices=TARGET_CHOICES, default='all')
    target_course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True,
                                      verbose_name="Target Class",
                                      help_text="Only required if target is 'Specific Class'")
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    attachment = models.FileField(upload_to='announcements/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    publish_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-publish_date']


class Message(models.Model):
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=200)
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    parent_message = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, 
                                       related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} -> {self.recipient}: {self.subject}"

    class Meta:
        ordering = ['-created_at']


class NotificationParent(models.Model):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification for {self.parent}"


@receiver(post_save, sender=Student)
def assign_admission_number(sender, instance, created, **kwargs):
    """Assign an admission number to a new student using AdmissionSetting (school-scoped)."""
    if created and (not instance.admission_number):
        school = instance.admin.school if instance.admin_id else None
        setting = AdmissionSetting.objects.filter(school=school).first() if school else AdmissionSetting.objects.filter(school__isnull=True).first()
        if not setting:
            setting = AdmissionSetting.objects.create(
                prefix='ADM', start_number=1000, next_number=1000, school=school
            )
        instance.admission_number = setting.get_next_admission()
        instance.save()


# ============================================
# SMS MODELS - Bulk SMS Integration
# ============================================

class SMSTemplate(models.Model):
    """Reusable SMS templates for different events"""
    TEMPLATE_TYPES = [
        ('fee_reminder', 'Fee Reminder'),
        ('attendance_alert', 'Attendance Alert'),
        ('result_notification', 'Result Notification'),
        ('general', 'General Announcement'),
        ('event', 'Event Notification'),
        ('emergency', 'Emergency Alert'),
    ]
    
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=30, choices=TEMPLATE_TYPES, default='general')
    content = models.TextField(help_text="Use placeholders: {student_name}, {parent_name}, {class_name}, {amount}, {date}, {school_name}")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

    class Meta:
        ordering = ['template_type', 'name']


class SMSQueue(models.Model):
    """Queue for bulk/scheduled SMS with status tracking"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    RECIPIENT_TYPE_CHOICES = [
        ('student', 'Student'),
        ('parent', 'Parent'),
        ('staff', 'Staff'),
        ('custom', 'Custom Number'),
    ]
    
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_TYPE_CHOICES)
    recipient_id = models.PositiveIntegerField(null=True, blank=True, help_text="ID of student/parent/staff")
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    template = models.ForeignKey(SMSTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    scheduled_at = models.DateTimeField(null=True, blank=True, help_text="Schedule for later delivery")
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    retry_count = models.PositiveIntegerField(default=0)
    batch_id = models.CharField(max_length=50, blank=True, null=True, help_text="Group ID for bulk SMS")
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SMS to {self.phone_number} - {self.status}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "SMS Queue"
        verbose_name_plural = "SMS Queue"


class SMSLog(models.Model):
    """Complete SMS delivery history"""
    queue_item = models.ForeignKey(SMSQueue, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs')
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    status = models.CharField(max_length=20)
    provider = models.CharField(max_length=50, help_text="SMS provider used")
    provider_message_id = models.CharField(max_length=100, blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    response_data = models.JSONField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SMS Log: {self.phone_number} - {self.status}"

    class Meta:
        ordering = ['-sent_at']
        verbose_name = "SMS Log"
        verbose_name_plural = "SMS Logs"


# ============================================
# FEE STRUCTURE MODELS
# ============================================

class FeeType(models.Model):
    """Different types of fees: Tuition, Transport, Uniform, etc. School-scoped for data isolation."""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fee_types',
        help_text="Null for legacy; each school has its own fee types"
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True, null=True)
    is_mandatory = models.BooleanField(default=True)
    is_recurring = models.BooleanField(default=True, help_text="Charged every term/year")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

    class Meta:
        ordering = ['name']
        unique_together = [['school', 'code']]


class FeeGroup(models.Model):
    """Fee groups for different categories: Day Scholar, Boarder, etc. School-scoped for data isolation."""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fee_groups',
        help_text="Null for legacy; each school has its own fee groups"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_total_fees(self):
        """Calculate total fees for this group"""
        return sum(item.amount for item in self.fee_items.all())

    class Meta:
        ordering = ['name']


class FeeGroupItem(models.Model):
    """Amount for each fee type in a group"""
    fee_group = models.ForeignKey(FeeGroup, on_delete=models.CASCADE, related_name='fee_items')
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name='group_items')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"{self.fee_group.name} - {self.fee_type.name}: {self.amount}"

    class Meta:
        unique_together = ['fee_group', 'fee_type']
        ordering = ['fee_group', 'fee_type']


class FeeStructure(models.Model):
    """Fee structure assignment per class/grade and academic year"""
    TERM_CHOICES = [
        ('term1', 'Term 1'),
        ('term2', 'Term 2'),
        ('term3', 'Term 3'),
        ('annual', 'Annual'),
    ]
    PAYMENT_SCHEDULE_CHOICES = [
        ('termly', 'Termly (full term amount)'),
        ('monthly', 'Monthly (installments)'),
    ]

    fee_group = models.ForeignKey(FeeGroup, on_delete=models.CASCADE, related_name='structures')
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.CASCADE, null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Class", help_text="Specific class")
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    term = models.CharField(max_length=10, choices=TERM_CHOICES, default='term1')
    payment_schedule = models.CharField(
        max_length=20, choices=PAYMENT_SCHEDULE_CHOICES, default='termly',
        help_text='Termly: full amount due by due_date. Monthly: installments per month.'
    )
    due_date = models.DateField(help_text='For termly: full payment due. For monthly: first installment due.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        target = self.course if self.course else self.grade_level
        return f"{self.fee_group.name} - {target} - {self.session}"

    class Meta:
        ordering = ['-session__start_year', 'term']


class FeePayment(models.Model):
    """Individual payment transactions - matches screenshot design"""
    PAYMENT_MODE_CHOICES = [
        ('cash', 'CASH'),
        ('paybill', 'PAYBILL'),
        ('mpesa', 'M-Pesa'),
        ('card', 'Card'),
        ('bank', 'Bank'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]
    
    TRANSACTION_TYPE_CHOICES = [
        ('credit', 'CREDIT'),
        ('debit', 'DEBIT'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='student_fee_payments')
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES, default='cash')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, default='credit')
    receipt_number = models.CharField(max_length=50, unique=True)
    transaction_ref = models.CharField(max_length=100, blank=True, null=True, help_text="Bank/Mpesa transaction reference")
    payment_date = models.DateTimeField()
    received_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='received_payments')
    paid_by = models.CharField(max_length=200, blank=True, null=True, help_text="Name of person who paid")
    description = models.TextField(blank=True, null=True)
    is_reversed = models.BooleanField(default=False)
    reversal_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.receipt_number} - {self.student} - {self.amount}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Fee Payment"
        verbose_name_plural = "Fee Payments"


class FeeBalance(models.Model):
    """Track student fee balances per session/term"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fee_balances')
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE, null=True, blank=True)
    total_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField(
        null=True, blank=True,
        help_text='When payment is due. Used for fee reminder notifications (1 week before).'
    )
    last_payment_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - Balance: {self.balance}"

    def update_balance(self):
        """Recalculate balance from payments"""
        payments = FeePayment.objects.filter(
            student=self.student,
            session=self.session,
            is_reversed=False
        ).aggregate(total=models.Sum('amount'))
        self.total_paid = payments['total'] or 0
        self.balance = self.total_fees - self.total_paid
        if payments['total']:
            last_payment = FeePayment.objects.filter(
                student=self.student,
                session=self.session,
                is_reversed=False
            ).order_by('-payment_date').first()
            self.last_payment_date = last_payment.payment_date if last_payment else None
        self.save()

    class Meta:
        unique_together = ['student', 'session']
        ordering = ['-session__start_year', 'student__admin__last_name']


# ============================================
# EXAM & RESULT MODELS
# ============================================

class ExamType(models.Model):
    """Types of exams: CAT, Mid-Term, End-Term, Mock, etc. - per school for isolation."""
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True,
        related_name='exam_types', help_text="Null = legacy/global; new schools create their own"
    )
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20)
    weight = models.FloatField(default=1.0, help_text="Weight for calculating weighted average")
    max_marks = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

    class Meta:
        ordering = ['name']
        unique_together = [['school', 'code']]


class ExamSchedule(models.Model):
    """Exam scheduling and management"""
    TERM_CHOICES = [
        ('term1', 'Term 1'),
        ('term2', 'Term 2'),
        ('term3', 'Term 3'),
    ]
    
    exam_type = models.ForeignKey(ExamType, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    academic_term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='exam_schedules', help_text="Academic term for this exam"
    )
    name = models.CharField(max_length=100, help_text="e.g., Term 1 End Term Exams 2024")
    start_date = models.DateField()
    end_date = models.DateField()
    is_published = models.BooleanField(default=False, help_text="Make results visible to students/parents")
    is_active = models.BooleanField(default=True)
    # Result entry control - teachers can only upload when admin opens
    result_entry_open = models.BooleanField(default=False, help_text="Allow teachers to enter results")
    result_entry_start_date = models.DateField(null=True, blank=True, help_text="When result entry opens")
    result_entry_end_date = models.DateField(null=True, blank=True, help_text="Upload deadline")
    result_entry_status = models.CharField(
        max_length=20,
        choices=[('draft', 'Draft'), ('open', 'Open'), ('closed', 'Closed')],
        default='draft',
        help_text="Result entry window status"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.session}"

    def is_result_entry_allowed(self):
        """Check if teachers can enter results (backend enforcement)."""
        from django.utils import timezone
        today = timezone.now().date()
        if not self.result_entry_open or self.result_entry_status != 'open':
            return False
        if self.academic_term and self.academic_term.status == 'closed':
            return False
        if self.result_entry_start_date and today < self.result_entry_start_date:
            return False
        if self.result_entry_end_date and today > self.result_entry_end_date:
            return False
        return True

    class Meta:
        ordering = ['-session__start_year', 'term', 'start_date']


class ResultEntryWindow(models.Model):
    """
    Controls when teachers can enter legacy results (StudentResult - test/exam).
    Used for staff_add_result and edit_student_result.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='result_entry_windows')
    academic_term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='result_entry_windows'
    )
    name = models.CharField(max_length=100, help_text="e.g., Term 1 Results 2024")
    result_entry_open = models.BooleanField(default=False)
    result_entry_start_date = models.DateField(null=True, blank=True)
    result_entry_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def is_entry_allowed(self):
        """Check if teachers can enter results."""
        from django.utils import timezone
        today = timezone.now().date()
        if not self.result_entry_open or self.status != 'open':
            return False
        if self.academic_term and self.academic_term.status == 'closed':
            return False
        if self.result_entry_start_date and today < self.result_entry_start_date:
            return False
        if self.result_entry_end_date and today > self.result_entry_end_date:
            return False
        return True

    class Meta:
        ordering = ['-session__start_year', '-created_at']


class GradingScale(models.Model):
    """Grading scale configuration - per school for isolation."""
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True,
        related_name='grading_scales', help_text="Null = legacy/global; new schools create their own"
    )
    name = models.CharField(max_length=50, help_text="e.g., Kenya CBC Grading")
    min_marks = models.FloatField()
    max_marks = models.FloatField()
    grade = models.CharField(max_length=5)
    points = models.FloatField(default=0)
    remarks = models.CharField(max_length=50, help_text="e.g., Excellent, Good, Average")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.grade}: {self.min_marks}-{self.max_marks} ({self.remarks})"

    class Meta:
        ordering = ['-min_marks']


class ExamResult(models.Model):
    """Enhanced exam result model"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_results')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    exam_schedule = models.ForeignKey(ExamSchedule, on_delete=models.CASCADE, related_name='results')
    marks = models.FloatField()
    grade = models.CharField(max_length=5, blank=True, null=True)
    points = models.FloatField(default=0)
    remarks = models.CharField(max_length=100, blank=True, null=True)
    position_in_class = models.PositiveIntegerField(null=True, blank=True)
    position_in_stream = models.PositiveIntegerField(null=True, blank=True)
    teacher_comment = models.TextField(blank=True, null=True)
    entered_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.subject} - {self.marks}"

    def calculate_grade(self):
        """Auto-calculate grade based on grading scale"""
        scale = GradingScale.objects.filter(
            min_marks__lte=self.marks,
            max_marks__gte=self.marks,
            is_active=True
        ).first()
        if scale:
            self.grade = scale.grade
            self.points = scale.points
            self.remarks = scale.remarks
        return self.grade

    def save(self, *args, **kwargs):
        if not self.grade:
            self.calculate_grade()
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ['student', 'subject', 'exam_schedule']
        ordering = ['student', 'subject']


class StudentTermResult(models.Model):
    """Aggregated term results for a student"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='term_results')
    exam_schedule = models.ForeignKey(ExamSchedule, on_delete=models.CASCADE)
    total_marks = models.FloatField(default=0)
    average_marks = models.FloatField(default=0)
    total_points = models.FloatField(default=0)
    mean_grade = models.CharField(max_length=5, blank=True, null=True)
    position_in_class = models.PositiveIntegerField(null=True, blank=True)
    position_in_grade = models.PositiveIntegerField(null=True, blank=True)
    class_teacher_comment = models.TextField(blank=True, null=True)
    principal_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.exam_schedule} - Avg: {self.average_marks}"

    def calculate_aggregates(self):
        """Calculate total, average, and mean grade"""
        results = ExamResult.objects.filter(
            student=self.student,
            exam_schedule=self.exam_schedule
        )
        if results.exists():
            self.total_marks = sum(r.marks for r in results)
            self.average_marks = self.total_marks / results.count()
            self.total_points = sum(r.points for r in results)
            # Calculate mean grade
            mean_points = self.total_points / results.count()
            scale = GradingScale.objects.filter(
                points__lte=mean_points,
                is_active=True
            ).order_by('-points').first()
            if scale:
                self.mean_grade = scale.grade
        self.save()

    class Meta:
        unique_together = ['student', 'exam_schedule']
        ordering = ['-exam_schedule__session__start_year', 'position_in_class']


# ============================================
# KNEC REPORT CARD MODELS
# ============================================

class KNECReportCardResult(models.Model):
    """
    Kenyan KNEC-based report card marks per subject per student per term.
    Stores Opener, Midterm, End-Term exam marks. Average = (Opener + Midterm + Endterm) / 3.
    Grade, points, remarks calculated using KNEC grading scale.
    """
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name='knec_report_results'
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name='knec_report_results'
    )
    academic_term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, related_name='knec_report_results',
        help_text="Term for this result"
    )
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name='knec_report_results',
        null=True, blank=True, help_text="Academic year/session"
    )
    opener_marks = models.FloatField(default=0, help_text="Opener exam marks (out of 100)")
    midterm_marks = models.FloatField(default=0, help_text="Midterm exam marks (out of 100)")
    endterm_marks = models.FloatField(default=0, help_text="End-term exam marks (out of 100)")
    average = models.FloatField(default=0, help_text="(Opener + Midterm + Endterm) / 3")
    grade = models.CharField(max_length=5, blank=True, null=True)
    points = models.FloatField(default=0)
    remarks = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.subject} - {self.get_term_display()}"

    def get_term_display(self):
        return str(self.academic_term) if self.academic_term else "N/A"

    def calculate_average_and_grade(self):
        """Calculate average and KNEC grade from opener, midterm, endterm."""
        from .knec_utils import get_knec_grade
        o = self.opener_marks or 0
        m = self.midterm_marks or 0
        e = self.endterm_marks or 0
        self.average = round((o + m + e) / 3, 2)  # KNEC: (Opener + Midterm + Endterm) / 3
        self.grade, self.points, self.remarks = get_knec_grade(self.average)

    def save(self, *args, **kwargs):
        self.calculate_average_and_grade()
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ['student', 'subject', 'academic_term']
        ordering = ['student', 'subject']
        verbose_name = "KNEC Report Card Result"
        verbose_name_plural = "KNEC Report Card Results"


# ============================================
# CLASS ATTENDANCE MODELS
# ============================================

class ClassAttendance(models.Model):
    """Daily class attendance (not subject-based)"""
    school_class = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='class_attendances')
    date = models.DateField()
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    term = models.ForeignKey(
        'AcademicTerm', on_delete=models.CASCADE, null=True, blank=True,
        related_name='class_attendances', help_text="Academic term"
    )
    marked_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.school_class} - {self.date}"

    @property
    def total_students(self):
        return self.attendance_records.count()
    
    @property
    def present_count(self):
        return self.attendance_records.filter(status='present').count()
    
    @property
    def absent_count(self):
        return self.attendance_records.filter(status='absent').count()
    
    @property
    def attendance_percentage(self):
        total = self.total_students
        if total > 0:
            return round((self.present_count / total) * 100, 1)
        return 0

    class Meta:
        unique_together = ['school_class', 'date']
        ordering = ['-date', 'school_class']
        verbose_name = "Class Attendance"
        verbose_name_plural = "Class Attendances"


class ClassAttendanceRecord(models.Model):
    """Individual student attendance record"""
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
        ('half_day', 'Half Day'),
    ]
    
    class_attendance = models.ForeignKey(ClassAttendance, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='class_attendance_records')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    arrival_time = models.TimeField(null=True, blank=True)
    remarks = models.CharField(max_length=200, blank=True, null=True)
    parent_notified = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student} - {self.class_attendance.date} - {self.status}"

    class Meta:
        unique_together = ['class_attendance', 'student']
        ordering = ['student__admin__last_name']


class AttendanceSummary(models.Model):
    """Monthly/Term attendance summary per student"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_summaries')
    school_class = models.ForeignKey(Course, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    month = models.PositiveIntegerField(null=True, blank=True)
    year = models.PositiveIntegerField()
    total_days = models.PositiveIntegerField(default=0)
    days_present = models.PositiveIntegerField(default=0)
    days_absent = models.PositiveIntegerField(default=0)
    days_late = models.PositiveIntegerField(default=0)
    days_excused = models.PositiveIntegerField(default=0)
    attendance_percentage = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.month}/{self.year} - {self.attendance_percentage}%"

    def calculate_summary(self):
        """Calculate attendance summary from records"""
        records = ClassAttendanceRecord.objects.filter(
            student=self.student,
            class_attendance__school_class=self.school_class,
            class_attendance__date__year=self.year
        )
        if self.month:
            records = records.filter(class_attendance__date__month=self.month)
        
        self.total_days = records.count()
        self.days_present = records.filter(status='present').count()
        self.days_absent = records.filter(status='absent').count()
        self.days_late = records.filter(status='late').count()
        self.days_excused = records.filter(status='excused').count()
        
        if self.total_days > 0:
            self.attendance_percentage = round((self.days_present / self.total_days) * 100, 1)
        self.save()

    class Meta:
        unique_together = ['student', 'school_class', 'session', 'month', 'year']
        ordering = ['-year', '-month']


# ============================================
# STUDENT SMS MODEL - Per-student SMS tracking
# ============================================

class StudentSMS(models.Model):
    """Track SMS messages sent to a specific student's guardian"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='sms_messages')
    guardian = models.ForeignKey('Guardian', on_delete=models.SET_NULL, null=True, blank=True)
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    delivery_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    delivery_time = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    sent_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SMS to {self.phone_number} for {self.student}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Student SMS"
        verbose_name_plural = "Student SMS Messages"


# ============================================
# STUDENT EXAM RESULT (Enhanced for screenshot matching)
# ============================================

class StudentExamResult(models.Model):
    """
    Exam result model matching the screenshot design:
    Academic Year | Term | Exam Type | Subject | Score | Out Of
    """
    TERM_CHOICES = [
        ('term1', 'TERM ONE'),
        ('term2', 'TERM TWO'),
        ('term3', 'TERM THREE'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='student_exam_results')
    academic_year = models.ForeignKey(Session, on_delete=models.CASCADE)
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    exam_type = models.ForeignKey(ExamType, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    score = models.FloatField()
    out_of = models.FloatField(default=100)
    grade = models.CharField(max_length=5, blank=True, null=True)
    entered_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.subject.name} - {self.score}/{self.out_of}"

    def calculate_grade(self):
        """Auto-calculate grade based on percentage"""
        percentage = (self.score / self.out_of) * 100
        scale = GradingScale.objects.filter(
            min_marks__lte=percentage,
            max_marks__gte=percentage,
            is_active=True
        ).first()
        if scale:
            self.grade = scale.grade
        return self.grade

    def save(self, *args, **kwargs):
        if not self.grade:
            self.calculate_grade()
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ['student', 'academic_year', 'term', 'exam_type', 'subject']
        ordering = ['-academic_year__start_year', 'term', 'subject__name']
        verbose_name = "Student Exam Result"
        verbose_name_plural = "Student Exam Results"


# ============================================
# SCHOOL SETTINGS MODEL
# ============================================

class SchoolSettings(models.Model):
    """School configuration settings - one per School (tenant)"""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='settings',
        help_text="Null = legacy single-school; one settings per school for multi-tenant"
    )
    school_name = models.CharField(max_length=200, default="School Name")
    school_motto = models.CharField(max_length=200, blank=True, null=True)
    school_address = models.TextField(blank=True, null=True)
    school_phone = models.CharField(max_length=20, blank=True, null=True)
    school_email = models.EmailField(blank=True, null=True)
    school_logo = models.ImageField(upload_to='school/', blank=True, null=True)
    principal_name = models.CharField(max_length=100, blank=True, null=True)
    principal_signature = models.ImageField(upload_to='school/', blank=True, null=True)
    receipt_prefix = models.CharField(max_length=10, default='RCP')
    receipt_next_number = models.PositiveIntegerField(default=1000)
    sms_sender_id = models.CharField(max_length=20, blank=True, null=True, help_text="SMS Sender ID")
    enable_sms_notifications = models.BooleanField(default=True)
    enable_attendance_sms = models.BooleanField(default=True)
    enable_fee_reminder_sms = models.BooleanField(default=True)
    fee_reminder_days_before = models.PositiveIntegerField(default=7)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.school_name

    def get_next_receipt_number(self):
        """Generate next receipt number"""
        receipt = f"{self.receipt_prefix}{self.receipt_next_number:06d}"
        self.receipt_next_number += 1
        self.save()
        return receipt

    class Meta:
        verbose_name = "School Settings"
        verbose_name_plural = "School Settings"


# Ensure only one SchoolSettings per school (or one global when school is None)
@receiver(post_save, sender=SchoolSettings)
def ensure_single_settings(sender, instance, created, **kwargs):
    if created:
        qs = SchoolSettings.objects.filter(school=instance.school).exclude(pk=instance.pk)
        if qs.exists():
            qs.delete()

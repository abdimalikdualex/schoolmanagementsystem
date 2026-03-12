import json
import os
import hashlib
import requests
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Q
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (HttpResponseRedirect, get_object_or_404,
                              redirect, render)
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import UpdateView
from django.conf import settings

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from .forms import *
from .models import *
from .models import (
    Stream, Parent, Timetable, Announcement, Message, GradeLevel, 
    StudentClassEnrollment, PromotionRecord, Guardian, StudentSMS, 
    StudentExamResult, FeePayment, ExamType, ContinuousAssessment,
    SubjectAttendance, Expense
)
from django.core.paginator import Paginator
from .sms_service import (
    send_sms, format_results_message, add_to_sms_queue, 
    send_bulk_sms_to_students, send_bulk_sms_to_parents, send_bulk_sms_to_class,
    process_sms_queue, get_sms_queue_stats, cancel_queued_sms,
    send_fee_reminder_sms, send_payment_receipt_sms, send_attendance_alert_sms,
    get_school_settings, render_sms_template
)
from .notifications import create_notification
from django.db import transaction
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncMonth
from django.utils import timezone
import uuid

# Backward compatibility alias
Section = Stream


def admin_home(request):
    school = getattr(request, 'school', None)
    staff_qs = Staff.objects.filter(admin__school=school) if school else Staff.objects.all()
    student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
    total_staff = staff_qs.count()
    total_students = student_qs.count()
    total_course = course_qs.count()
    subjects_qs = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
    total_subject = subjects_qs.count()
    total_course = course_qs.count()
    attendance_list = Attendance.objects.filter(subject__in=subjects_qs)
    total_attendance = attendance_list.count()
    attendance_list = []
    subject_list = []
    for subject in subjects_qs:
        attendance_count = Attendance.objects.filter(subject=subject).count()
        subject_list.append(subject.name[:7])
        attendance_list.append(attendance_count)

    # Total Subjects and students in Each Course
    course_all = course_qs
    course_name_list = []
    subject_count_list = []
    student_count_list_in_course = []

    for course in course_all:
        subject_count = Subject.objects.filter(course_id=course.id).count()
        students = Student.objects.filter(course_id=course.id).count()
        course_name_list.append(course.name)
        subject_count_list.append(subject_count)
        student_count_list_in_course.append(students)

    subject_all = subjects_qs
    subject_list = []
    student_count_list_in_subject = []
    for subject in subject_all:
        course = Course.objects.get(id=subject.course.id)
        student_count = Student.objects.filter(course_id=course.id).count()
        subject_list.append(subject.name)
        student_count_list_in_subject.append(student_count)


    # For Students
    student_attendance_present_list=[]
    student_attendance_leave_list=[]
    student_name_list=[]

    students = student_qs
    for student in students:
        
        attendance = AttendanceReport.objects.filter(student_id=student.id, status=True).count()
        absent = AttendanceReport.objects.filter(student_id=student.id, status=False).count()
        leave = LeaveReportStudent.objects.filter(student_id=student.id, status=1).count()
        student_attendance_present_list.append(attendance)
        student_attendance_leave_list.append(leave+absent)
        student_name_list.append(student.admin.first_name)

    # Results stats (KNEC report cards)
    from .models import KNECReportCardResult, AcademicTerm
    results_count = 0
    terms_with_results = 0
    if school:
        results_count = KNECReportCardResult.objects.filter(student__admin__school=school).count()
        term_ids = KNECReportCardResult.objects.filter(student__admin__school=school).values_list('academic_term_id', flat=True).distinct()
        terms_with_results = len(set(term_ids))

    # Onboarding: show setup steps when school has no data
    is_new_school = school and total_students == 0 and total_staff == 0 and total_course == 0
    context = {
        'page_title': "Administrative Dashboard",
        'is_new_school': is_new_school,
        'total_students': total_students,
        'results_count': results_count,
        'terms_with_results': terms_with_results,
        'total_staff': total_staff,
        'total_course': total_course,
        'total_subject': total_subject,
        'subject_list': subject_list,
        'attendance_list': attendance_list,
        'student_attendance_present_list': student_attendance_present_list,
        'student_attendance_leave_list': student_attendance_leave_list,
        "student_name_list": student_name_list,
        "student_count_list_in_subject": student_count_list_in_subject,
        "student_count_list_in_course": student_count_list_in_course,
        "course_name_list": course_name_list,

    }
    return render(request, 'hod_template/home_content.html', context)


def add_staff(request):
    school = getattr(request, 'school', None)
    form = StaffForm(request.POST or None, request.FILES or None, school=school)
    context = {'form': form, 'page_title': 'Add Staff'}
    school = getattr(request, 'school', None)
    if request.method == 'POST':
        if school and not school.can_add_teacher():
            plan = school.subscription_plan
            limit_str = "Unlimited" if plan.teacher_limit == 0 else str(plan.teacher_limit)
            messages.error(
                request,
                f"Teacher limit reached ({limit_str}). Upgrade your plan to add more teachers."
            )
            return render(request, 'hod_template/add_staff_template.html', context)
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password')
            course = form.cleaned_data.get('course')
            passport = request.FILES.get('profile_pic')
            
            try:
                passport_url = ''
                if passport:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                
                user = CustomUser.objects.create_user(
                    email=email, password=password, user_type='2', first_name=first_name, last_name=last_name, profile_pic=passport_url)
                user.gender = gender
                user.address = address
                user.school = getattr(request, 'school', None)
                user.save()
                
                # Get or create the staff profile and update it
                staff, created = Staff.objects.get_or_create(admin=user)
                staff.course = course
                staff.save()
                
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_staff'))

            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Please fulfil all requirements")

    return render(request, 'hod_template/add_staff_template.html', context)


def add_finance_officer(request):
    """Admin: Create Finance Officer account (user_type='5')"""
    from .forms import FinanceOfficerForm
    form = FinanceOfficerForm(request.POST or None, request.FILES or None)
    context = {'form': form, 'page_title': 'Add Finance Officer'}
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name').strip()
            last_name = form.cleaned_data.get('last_name').strip()
            email = form.cleaned_data.get('email').strip().lower()
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password')
            address = form.cleaned_data.get('address') or 'N/A'
            phone_number = form.cleaned_data.get('phone_number') or ''
            passport = request.FILES.get('profile_pic')
            try:
                passport_url = ''
                if passport:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                user = CustomUser.objects.create_user(
                    email=email, password=password, user_type='5',
                    first_name=first_name, last_name=last_name, profile_pic=passport_url
                )
                user.gender = gender
                user.address = address
                user.phone_number = phone_number
                user.school = getattr(request, 'school', None)
                user.save()
                messages.success(request, f"Finance Officer {first_name} {last_name} added successfully.")
                return redirect(reverse('add_finance_officer'))
            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Please fulfil all requirements")
    return render(request, 'hod_template/add_finance_officer_template.html', context)


def manage_finance_officers(request):
    """Admin: List Finance Officers"""
    school = getattr(request, 'school', None)
    officers = CustomUser.objects.filter(user_type='5', school=school).order_by('last_name') if school else CustomUser.objects.filter(user_type='5').order_by('last_name')
    context = {'officers': officers, 'page_title': 'Manage Finance Officers'}
    return render(request, 'hod_template/manage_finance_officers.html', context)


def add_admission_officer(request):
    """Admin: Create Admission Officer account (user_type='6')"""
    from .forms import AdmissionOfficerForm
    form = AdmissionOfficerForm(request.POST or None, request.FILES or None)
    context = {'form': form, 'page_title': 'Add Admission Officer'}
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name').strip()
            last_name = form.cleaned_data.get('last_name').strip()
            email = form.cleaned_data.get('email').strip().lower()
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password')
            address = form.cleaned_data.get('address') or 'N/A'
            phone_number = form.cleaned_data.get('phone_number') or ''
            passport = request.FILES.get('profile_pic')
            try:
                passport_url = ''
                if passport:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                user = CustomUser.objects.create_user(
                    email=email, password=password, user_type='6',
                    first_name=first_name, last_name=last_name, profile_pic=passport_url
                )
                user.gender = gender
                user.address = address
                user.phone_number = phone_number
                user.school = getattr(request, 'school', None)
                user.save()
                messages.success(request, f"Admission Officer {first_name} {last_name} added successfully.")
                return redirect(reverse('add_admission_officer'))
            except Exception as e:
                messages.error(request, f"Could Not Add: {str(e)}")
        else:
            messages.error(request, "Please fulfil all requirements")
    return render(request, 'hod_template/add_admission_officer_template.html', context)


def manage_admission_officers(request):
    """Admin: List Admission Officers"""
    school = getattr(request, 'school', None)
    officers = CustomUser.objects.filter(user_type='6', school=school).order_by('last_name') if school else CustomUser.objects.filter(user_type='6').order_by('last_name')
    context = {'officers': officers, 'page_title': 'Manage Admission Officers'}
    return render(request, 'hod_template/manage_admission_officers.html', context)


def _generate_admission_number():
    """MVP: Auto-generate admission number format 2026-001, 2026-002, etc. (Kenyan school best practice)."""
    year = timezone.now().year
    last_student = Student.objects.filter(
        admission_number__startswith=f"{year}-"
    ).order_by("-id").first()
    if last_student and last_student.admission_number:
        try:
            parts = last_student.admission_number.split("-")
            if len(parts) == 2:
                last_number = int(parts[1])
                new_number = last_number + 1
            else:
                new_number = 1
        except (ValueError, IndexError):
            new_number = 1
    else:
        new_number = 1
    return f"{year}-{new_number:03d}"


def add_student(request):
    """Add student - same format as Add Staff (email, password, profile_pic, etc.)."""
    from .forms import AddStudentForm
    from .models import StudentSubjectEnrollment

    school = getattr(request, 'school', None)
    form = AddStudentForm(request.POST or None, request.FILES or None, school=school)
    active_term = AcademicTerm.get_active_term(school=school)
    context = {
        'form': form,
        'page_title': 'Add Student',
        'active_term': active_term,
    }

    school = getattr(request, 'school', None)
    if request.method == 'POST':
        if school and not school.can_add_student():
            plan = school.subscription_plan
            limit_str = "Unlimited" if plan.student_limit == 0 else str(plan.student_limit)
            messages.error(
                request,
                f"Student limit reached ({limit_str}). Upgrade your plan to add more students."
            )
            return render(request, 'hod_template/add_student_template.html', context)
        if form.is_valid():
            first_name = form.cleaned_data['first_name'].strip()
            last_name = form.cleaned_data['last_name'].strip()
            email = form.cleaned_data['email'].strip().lower()
            gender = form.cleaned_data['gender']
            password = form.cleaned_data['password']
            address = form.cleaned_data.get('address') or 'N/A'
            course = form.cleaned_data['course']
            guardian_name = form.cleaned_data['guardian_name'].strip()
            guardian_email = form.cleaned_data.get('guardian_email') or ''
            guardian_phone = form.cleaned_data['guardian_phone'].strip()
            passport = request.FILES.get('profile_pic')
            admission_number = form.cleaned_data['admission_number'].strip()

            if not active_term:
                messages.error(request, "No active term. Please activate an academic term first.")
                return render(request, 'hod_template/add_student_template.html', context)

            try:
                passport_url = ''
                if passport:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)

                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        email=email,
                        password=password,
                        user_type='3',
                        first_name=first_name,
                        last_name=last_name,
                        profile_pic=passport_url,
                    )
                    user.gender = gender
                    user.address = address
                    user.phone_number = form.cleaned_data.get('phone_number') or ''
                    user.school = getattr(request, 'school', None)
                    user.save()

                    # Signal create_user_profile already created Student - update it
                    student = Student.objects.get(admin=user)
                    student.admission_number = admission_number
                    student.course = course
                    student.current_class = course
                    student.status = 'active'
                    student.admission_date = timezone.now().date()
                    student.save()

                    Guardian.objects.create(
                        student=student,
                        name=guardian_name,
                        email=guardian_email or None,
                        phone_number=guardian_phone,
                        is_primary=True,
                    )

                    if school:
                        session = Session.objects.filter(
                            school=school,
                            academic_year=timezone.now().year
                        ).first() or Session.objects.filter(school=school).first()
                    else:
                        session = Session.objects.filter(
                            academic_year=timezone.now().year
                        ).first() or Session.objects.first()
                    if session:
                        student.session = session
                        student.save()

                    if not session:
                        raise ValueError("No Session found. Please add an academic session first.")

                    enrollment = StudentClassEnrollment.objects.create(
                        student=student,
                        school_class=course,
                        academic_year=session,
                        term=active_term,
                        status='active',
                    )

                    subjects = Subject.objects.filter(course=course).filter(
                        Q(term=active_term) | Q(term__isnull=True)
                    )
                    for subj in subjects:
                        StudentSubjectEnrollment.objects.get_or_create(
                            student=student,
                            subject=subj,
                            term=active_term,
                            defaults={'enrollment': enrollment},
                        )

                    # Auto-bill: create FeeBalance immediately so student sees fees in portal
                    _create_fee_balance_for_enrollment(
                        student, course, session, active_term
                    )

                # Notify class teacher if assigned
                if course.class_teacher_id and school:
                    create_notification(
                        course.class_teacher.admin,
                        "New Student Registered",
                        f"{first_name} {last_name} (Admission: {admission_number}) has been enrolled in {course.name}.",
                        reverse('manage_student'),
                        school=school,
                    )

                messages.success(request, f"Student {first_name} {last_name} added successfully. Admission No: {admission_number}")
                return redirect(reverse('add_student'))
            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Please fulfil all requirements")

    return render(request, 'hod_template/add_student_template.html', context)


def add_course(request):
    school = getattr(request, 'school', None)
    form = CourseForm(request.POST or None, school=school)
    context = {
        'form': form,
        'page_title': 'Add Class',
        'grade_levels': GradeLevel.objects.filter(school=school, is_active=True) if school else GradeLevel.objects.none(),
        'streams': Stream.objects.filter(school=school) if school else Stream.objects.none(),
        'teachers': Staff.objects.filter(admin__school=school) if school else Staff.objects.none(),
        'sessions': Session.objects.filter(school=school) if school else Session.objects.none()
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                course = form.save(commit=False)
                if school:
                    course.school = school
                # Auto-generate name if grade_level and stream are selected
                if course.grade_level and course.stream:
                    course.name = f"{course.grade_level.code} {course.stream.name}"
                course.save()
                messages.success(request, "Class Added Successfully")
                return redirect(reverse('add_course'))
            except Exception as e:
                messages.error(request, f"Could Not Add: {str(e)}")
        else:
            messages.error(request, "Could Not Add")
    return render(request, 'hod_template/add_course_template.html', context)


def add_subject(request):
    school = getattr(request, 'school', None)
    form = SubjectForm(request.POST or None, school=school)
    context = {
        'form': form,
        'page_title': 'Add Subject'
    }
    if request.method == 'POST':
        if form.is_valid():
            name = form.cleaned_data.get('name')
            course = form.cleaned_data.get('course')
            staff = form.cleaned_data.get('staff')
            try:
                subject = Subject()
                subject.name = name
                subject.staff = staff
                subject.course = course
                subject.save()
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_subject'))

            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Fill Form Properly")

    return render(request, 'hod_template/add_subject_template.html', context)


def manage_staff(request):
    school = getattr(request, 'school', None)
    allStaff = CustomUser.objects.filter(user_type=2, school=school) if school else CustomUser.objects.filter(user_type=2)
    context = {
        'allStaff': allStaff,
        'page_title': 'Manage Staff'
    }
    return render(request, "hod_template/manage_staff.html", context)


def manage_student(request):
    school = getattr(request, 'school', None)
    qs = CustomUser.objects.filter(user_type=3, student__isnull=False, school=school) if school else CustomUser.objects.filter(user_type=3, student__isnull=False)
    students = qs.select_related('student', 'student__course')
    context = {
        'students': students,
        'page_title': 'Manage Students'
    }
    return render(request, "hod_template/manage_student.html", context)


def admission_setting_view(request):
    # Allow HOD and Staff to configure admission numbering
    if not request.user.is_authenticated or int(request.user.user_type) not in [1, 2]:
        return redirect('login_page')

    school = getattr(request, 'school', None)
    setting = AdmissionSetting.objects.filter(school=school).first() if school else AdmissionSetting.objects.first()
    if request.method == 'POST':
        prefix = request.POST.get('prefix', 'ADM').strip()
        start = request.POST.get('start_number')
        try:
            start = int(start)
        except Exception:
            start = None

        if not setting:
            setting = AdmissionSetting.objects.create(
                prefix=prefix, start_number=start or 1000, next_number=start or 1000,
                created_by=request.user, school=school
            )
            messages.success(request, 'Admission setting created')
        else:
            if prefix:
                setting.prefix = prefix
            if start:
                setting.start_number = start
                setting.next_number = start
            setting.created_by = request.user
            setting.save()
            messages.success(request, 'Admission setting updated')

    context = {
        'setting': setting,
        'page_title': 'Admission Settings'
    }
    return render(request, 'hod_template/admission_setting.html', context)


def student_search(request):
    # Search students by admission number or name
    if not request.user.is_authenticated or int(request.user.user_type) not in [1, 2]:
        return redirect('login_page')

    school = getattr(request, 'school', None)
    q = request.GET.get('q', '').strip()
    students = []
    if q:
        qs = Student.objects.filter(
            models.Q(admission_number__iexact=q) |
            models.Q(admin__first_name__icontains=q) |
            models.Q(admin__last_name__icontains=q)
        )
        if school:
            qs = qs.filter(admin__school=school)
        students = qs

    context = {
        'students': students,
        'query': q,
        'page_title': 'Search Students'
    }
    return render(request, 'hod_template/student_search.html', context)


def student_profile(request, student_id):
    # Display student details, results, fees and notifications
    if not request.user.is_authenticated or int(request.user.user_type) not in [1, 2]:
        return redirect('login_page')

    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    results = StudentResult.objects.filter(student=student).select_related('subject')
    fees = StudentFees.objects.filter(student=student).order_by('-created_at')
    notifications = NotificationStudent.objects.filter(student=student).order_by('-created_at')[:10]

    # Summaries (use Decimal for safe arithmetic)
    total_due = Decimal('0.00')
    total_paid = Decimal('0.00')
    for f in fees:
        total_due += f.amount_due
        total_paid += f.amount_paid

    total_outstanding = total_due - total_paid

    context = {
        'student': student,
        'results': results,
        'fees': fees,
        'notifications': notifications,
        'total_due': total_due,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'page_title': 'Student Profile'
    }
    return render(request, 'hod_template/student_profile.html', context)


def manage_course(request):
    school = getattr(request, 'school', None)
    courses = Course.objects.filter(school=school).select_related('grade_level', 'stream', 'class_teacher__admin') if school else Course.objects.all().select_related('grade_level', 'stream', 'class_teacher__admin')
    context = {
        'courses': courses,
        'page_title': 'Manage Classes'
    }
    return render(request, "hod_template/manage_course.html", context)


def manage_subject(request):
    school = getattr(request, 'school', None)
    subjects = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
    context = {
        'subjects': subjects,
        'page_title': 'Manage Subjects'
    }
    return render(request, "hod_template/manage_subject.html", context)


def edit_staff(request, staff_id):
    school = getattr(request, 'school', None)
    qs = Staff.objects.filter(admin__school=school) if school else Staff.objects.all()
    staff = get_object_or_404(qs, id=staff_id)
    form = StaffForm(request.POST or None, request.FILES or None, instance=staff, school=school)
    context = {
        'form': form,
        'staff_id': staff_id,
        'page_title': 'Edit Staff'
    }
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            username = form.cleaned_data.get('username')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password') or None
            course = form.cleaned_data.get('course')
            passport = request.FILES.get('profile_pic') or None
            try:
                user = CustomUser.objects.get(id=staff.admin.id)
                user.username = username
                user.email = email
                if password != None:
                    user.set_password(password)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    user.profile_pic = passport_url
                user.first_name = first_name
                user.last_name = last_name
                user.gender = gender
                user.address = address
                staff.course = course
                user.save()
                staff.save()
                messages.success(request, "Successfully Updated")
                return redirect(reverse('edit_staff', args=[staff_id]))
            except Exception as e:
                messages.error(request, "Could Not Update " + str(e))
        else:
            messages.error(request, "Please fil form properly")
    else:
        return render(request, "hod_template/edit_staff_template.html", context)


def edit_student(request, student_id):
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    form = StudentForm(request.POST or None, instance=student, school=school)
    context = {
        'form': form,
        'student_id': student_id,
        'page_title': 'Edit Student'
    }
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            username = form.cleaned_data.get('username')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password') or None
            course = form.cleaned_data.get('course')
            session = form.cleaned_data.get('session')
            passport = request.FILES.get('profile_pic') or None
            try:
                user = CustomUser.objects.get(id=student.admin.id)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    user.profile_pic = passport_url
                user.username = username
                user.email = email
                if password != None:
                    user.set_password(password)
                user.first_name = first_name
                user.last_name = last_name
                student.session = session
                user.gender = gender
                user.address = address
                student.course = course
                user.save()
                student.save()
                messages.success(request, "Successfully Updated")
                return redirect(reverse('edit_student', args=[student_id]))
            except Exception as e:
                messages.error(request, "Could Not Update " + str(e))
        else:
            messages.error(request, "Please Fill Form Properly!")
    else:
        return render(request, "hod_template/edit_student_template.html", context)


def edit_course(request, course_id):
    school = getattr(request, 'school', None)
    qs = Course.objects.filter(school=school) if school else Course.objects.all()
    instance = get_object_or_404(qs, id=course_id)
    form = CourseForm(request.POST or None, instance=instance, school=school)
    context = {
        'form': form,
        'course_id': course_id,
        'page_title': 'Edit Class',
        'grade_levels': GradeLevel.objects.filter(school=school, is_active=True) if school else GradeLevel.objects.none(),
        'streams': Stream.objects.filter(school=school) if school else Stream.objects.none(),
        'teachers': Staff.objects.filter(admin__school=school) if school else Staff.objects.none(),
        'sessions': Session.objects.filter(school=school) if school else Session.objects.none()
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                course = form.save(commit=False)
                # Auto-generate name if grade_level and stream are selected
                if course.grade_level and course.stream:
                    course.name = f"{course.grade_level.code} {course.stream.name}"
                course.save()
                messages.success(request, "Class Updated Successfully")
            except Exception as e:
                messages.error(request, f"Could Not Update: {str(e)}")
        else:
            messages.error(request, "Could Not Update")

    return render(request, 'hod_template/edit_course_template.html', context)


def edit_subject(request, subject_id):
    school = getattr(request, 'school', None)
    qs = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
    instance = get_object_or_404(qs, id=subject_id)
    form = SubjectForm(request.POST or None, instance=instance, school=school)
    context = {
        'form': form,
        'subject_id': subject_id,
        'page_title': 'Edit Subject'
    }
    if request.method == 'POST':
        if form.is_valid():
            name = form.cleaned_data.get('name')
            course = form.cleaned_data.get('course')
            staff = form.cleaned_data.get('staff')
            try:
                subject = Subject.objects.get(id=subject_id)
                subject.name = name
                subject.staff = staff
                subject.course = course
                subject.save()
                messages.success(request, "Successfully Updated")
                return redirect(reverse('edit_subject', args=[subject_id]))
            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Fill Form Properly")
    return render(request, 'hod_template/edit_subject_template.html', context)


def add_session(request):
    form = SessionForm(request.POST or None)
    context = {'form': form, 'page_title': 'Add Session'}
    if request.method == 'POST':
        if form.is_valid():
            try:
                session = form.save(commit=False)
                session.school = getattr(request, 'school', None)
                session.save()
                messages.success(request, "Session Created")
                return redirect(reverse('add_session'))
            except Exception as e:
                messages.error(request, 'Could Not Add ' + str(e))
        else:
            messages.error(request, 'Fill Form Properly ')
    return render(request, "hod_template/add_session_template.html", context)


def manage_session(request):
    school = getattr(request, 'school', None)
    sessions = Session.objects.filter(school=school) if school else Session.objects.all()
    context = {'sessions': sessions, 'page_title': 'Manage Sessions'}
    return render(request, "hod_template/manage_session.html", context)


def edit_session(request, session_id):
    school = getattr(request, 'school', None)
    qs = Session.objects.filter(school=school) if school else Session.objects.all()
    instance = get_object_or_404(qs, id=session_id)
    form = SessionForm(request.POST or None, instance=instance)
    context = {'form': form, 'session_id': session_id,
               'page_title': 'Edit Session'}
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Session Updated")
                return redirect(reverse('edit_session', args=[session_id]))
            except Exception as e:
                messages.error(
                    request, "Session Could Not Be Updated " + str(e))
                return render(request, "hod_template/edit_session_template.html", context)
        else:
            messages.error(request, "Invalid Form Submitted ")
            return render(request, "hod_template/edit_session_template.html", context)

    else:
        return render(request, "hod_template/edit_session_template.html", context)


# ============ Academic Terms ============
def manage_academic_terms(request):
    """List all academic terms"""
    school = getattr(request, 'school', None)
    terms = AcademicTerm.objects.filter(school=school) if school else AcademicTerm.objects.all()
    active_term = AcademicTerm.get_active_term(school=getattr(request, 'school', None))
    context = {
        'terms': terms,
        'active_term': active_term,
        'page_title': 'Academic Terms'
    }
    return render(request, 'hod_template/manage_academic_terms.html', context)


def add_academic_term(request):
    """Create a new academic term"""
    from .forms import AcademicTermForm
    school = getattr(request, 'school', None)
    form = AcademicTermForm(request.POST or None)
    context = {'form': form, 'page_title': 'Add Academic Term'}
    if request.method == 'POST':
        if form.is_valid():
            try:
                term = form.save(commit=False)
                if school:
                    term.school = school
                term.save()
                messages.success(request, "Academic term created successfully.")
                return redirect(reverse('manage_academic_terms'))
            except Exception as e:
                messages.error(request, f"Could not create term: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    messages.error(request, f"{form.fields.get(field, field)}: {err}")
    return render(request, 'hod_template/add_academic_term_template.html', context)


def edit_academic_term(request, term_id):
    """Edit an academic term"""
    from .forms import AcademicTermForm
    school = getattr(request, 'school', None)
    qs = AcademicTerm.objects.filter(school=school) if school else AcademicTerm.objects.all()
    term = get_object_or_404(qs, id=term_id)
    form = AcademicTermForm(request.POST or None, instance=term)
    context = {'form': form, 'term': term, 'term_id': term_id, 'page_title': 'Edit Academic Term'}
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Academic term updated successfully.")
                return redirect(reverse('manage_academic_terms'))
            except Exception as e:
                messages.error(request, f"Could not update term: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    messages.error(request, f"{form.fields.get(field, field)}: {err}")
    return render(request, 'hod_template/edit_academic_term_template.html', context)


def activate_academic_term(request, term_id):
    """Set term as active (closes all others)"""
    school = getattr(request, 'school', None)
    qs = AcademicTerm.objects.filter(school=school) if school else AcademicTerm.objects.all()
    term = get_object_or_404(qs, id=term_id)
    try:
        term.activate()
        messages.success(request, f"{term} is now the active term.")
    except Exception as e:
        messages.error(request, f"Could not activate term: {str(e)}")
    return redirect(reverse('manage_academic_terms'))


def close_academic_term(request, term_id):
    """Close an academic term - MVP: Locks attendance and marks editing"""
    school = getattr(request, 'school', None)
    qs = AcademicTerm.objects.filter(school=school) if school else AcademicTerm.objects.all()
    term = get_object_or_404(qs, id=term_id)
    try:
        term.close()
        messages.success(request, f"{term.term_name} closed. Attendance and marks are now locked.")
    except Exception as e:
        messages.error(request, f"Could not close term: {str(e)}")
    return redirect(reverse('manage_academic_terms'))


def delete_academic_term(request, term_id):
    """Delete an academic term. School admin: only terms in their school."""
    school = getattr(request, 'school', None)
    qs = AcademicTerm.objects.filter(school=school) if school else AcademicTerm.objects.all()
    term = get_object_or_404(qs, id=term_id)
    term_name = str(term)
    term.delete()
    messages.success(request, f"Term '{term_name}' has been deleted.")
    return redirect(reverse('manage_academic_terms'))


@csrf_exempt
def check_email_availability(request):
    email = request.POST.get("email")
    try:
        exists = CustomUser.objects.filter(email__iexact=email).exists()
        return JsonResponse({'available': not exists})
    except Exception as e:
        return JsonResponse({'available': True, 'error': str(e)}, status=500)


@csrf_exempt
def student_feedback_message(request):
    school = getattr(request, 'school', None)
    if request.method != 'POST':
        feedbacks = FeedbackStudent.objects.filter(student__admin__school=school) if school else FeedbackStudent.objects.all()
        context = {
            'feedbacks': feedbacks,
            'page_title': 'Student Feedback Messages'
        }
        return render(request, 'hod_template/student_feedback_template.html', context)
    else:
        feedback_id = request.POST.get('id')
        try:
            qs = FeedbackStudent.objects.filter(student__admin__school=school) if school else FeedbackStudent.objects.all()
            feedback = get_object_or_404(qs, id=feedback_id)
            reply = request.POST.get('reply')
            feedback.reply = reply
            feedback.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def staff_feedback_message(request):
    school = getattr(request, 'school', None)
    if request.method != 'POST':
        feedbacks = FeedbackStaff.objects.filter(staff__admin__school=school) if school else FeedbackStaff.objects.all()
        context = {
            'feedbacks': feedbacks,
            'page_title': 'Staff Feedback Messages'
        }
        return render(request, 'hod_template/staff_feedback_template.html', context)
    else:
        feedback_id = request.POST.get('id')
        try:
            qs = FeedbackStaff.objects.filter(staff__admin__school=school) if school else FeedbackStaff.objects.all()
            feedback = get_object_or_404(qs, id=feedback_id)
            reply = request.POST.get('reply')
            feedback.reply = reply
            feedback.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def view_staff_leave(request):
    school = getattr(request, 'school', None)
    if request.method != 'POST':
        allLeave = LeaveReportStaff.objects.filter(staff__admin__school=school) if school else LeaveReportStaff.objects.all()
        context = {
            'allLeave': allLeave,
            'page_title': 'Leave Applications From Staff'
        }
        return render(request, "hod_template/staff_leave_view.html", context)
    else:
        id = request.POST.get('id')
        status = request.POST.get('status')
        if (status == '1'):
            status = 1
        else:
            status = -1
        try:
            qs = LeaveReportStaff.objects.filter(staff__admin__school=school) if school else LeaveReportStaff.objects.all()
            leave = get_object_or_404(qs, id=id)
            leave.status = status
            leave.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def view_student_leave(request):
    school = getattr(request, 'school', None)
    if request.method != 'POST':
        allLeave = LeaveReportStudent.objects.filter(student__admin__school=school) if school else LeaveReportStudent.objects.all()
        context = {
            'allLeave': allLeave,
            'page_title': 'Leave Applications From Students'
        }
        return render(request, "hod_template/student_leave_view.html", context)
    else:
        id = request.POST.get('id')
        status = request.POST.get('status')
        if (status == '1'):
            status = 1
        else:
            status = -1
        try:
            qs = LeaveReportStudent.objects.filter(student__admin__school=school) if school else LeaveReportStudent.objects.all()
            leave = get_object_or_404(qs, id=id)
            leave.status = status
            leave.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


def admin_view_attendance(request):
    school = getattr(request, 'school', None)
    subjects = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
    sessions = Session.objects.filter(school=school) if school else Session.objects.all()
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'page_title': 'View Attendance'
    }

    return render(request, "hod_template/admin_view_attendance.html", context)


@csrf_exempt
def get_admin_attendance(request):
    school = getattr(request, 'school', None)
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    attendance_date_id = request.POST.get('attendance_date_id')
    try:
        subject_qs = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
        session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
        subject = get_object_or_404(subject_qs, id=subject_id)
        session = get_object_or_404(session_qs, id=session_id)
        attendance = get_object_or_404(
            Attendance, id=attendance_date_id, session=session)
        attendance_reports = AttendanceReport.objects.filter(
            attendance=attendance)
        json_data = []
        for report in attendance_reports:
            data = {
                "status":  str(report.status),
                "name": str(report.student)
            }
            json_data.append(data)
        return JsonResponse(json_data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def admin_view_profile(request):
    admin = get_object_or_404(Admin, admin=request.user)
    form = AdminForm(request.POST or None, request.FILES or None,
                     instance=admin)
    context = {'form': form,
               'page_title': 'View/Edit Profile'
               }
    if request.method == 'POST':
        try:
            if form.is_valid():
                first_name = form.cleaned_data.get('first_name')
                last_name = form.cleaned_data.get('last_name')
                email = form.cleaned_data.get('email')
                gender = form.cleaned_data.get('gender')
                phone_number = form.cleaned_data.get('phone_number')
                address = form.cleaned_data.get('address')
                password = form.cleaned_data.get('password') or None
                passport = request.FILES.get('profile_pic') or None
                custom_user = admin.admin
                if password != None:
                    custom_user.set_password(password)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    custom_user.profile_pic = passport_url
                custom_user.first_name = first_name
                custom_user.last_name = last_name
                custom_user.email = email
                custom_user.gender = gender
                custom_user.phone_number = phone_number or None
                custom_user.address = address or ''
                custom_user.save()
                messages.success(request, "Profile Updated!")
                return redirect(reverse('admin_view_profile'))
            else:
                messages.error(request, "Invalid Data Provided")
        except Exception as e:
            messages.error(
                request, "Error Occured While Updating Profile " + str(e))
    return render(request, "hod_template/admin_view_profile.html", context)


def admin_notify_staff(request):
    school = getattr(request, 'school', None)
    staff = CustomUser.objects.filter(user_type=2, school=school) if school else CustomUser.objects.filter(user_type=2)
    context = {
        'page_title': "Send Notifications To Staff",
        'allStaff': staff
    }
    return render(request, "hod_template/staff_notification.html", context)


def admin_notify_student(request):
    school = getattr(request, 'school', None)
    student = CustomUser.objects.filter(user_type=3, school=school) if school else CustomUser.objects.filter(user_type=3)
    context = {
        'page_title': "Send Notifications To Students",
        'students': student
    }
    return render(request, "hod_template/student_notification.html", context)


@csrf_exempt
def send_student_notification(request):
    id = request.POST.get('id')
    message = request.POST.get('message')
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, admin_id=id)
    try:
        url = "https://fcm.googleapis.com/fcm/send"
        body = {
            'notification': {
                'title': "Student Management System",
                'body': message,
                'click_action': reverse('student_view_notification'),
                'icon': static('dist/img/AdminLTELogo.png')
            },
            'to': student.admin.fcm_token
        }
        headers = {'Authorization':
                   'key=AAAA3Bm8j_M:APA91bElZlOLetwV696SoEtgzpJr2qbxBfxVBfDWFiopBWzfCfzQp2nRyC7_A2mlukZEHV4g1AmyC6P_HonvSkY2YyliKt5tT3fe_1lrKod2Daigzhb2xnYQMxUWjCAIQcUexAMPZePB',
                   'Content-Type': 'application/json'}
        data = requests.post(url, data=json.dumps(body), headers=headers)
        notification = NotificationStudent(student=student, message=message)
        notification.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def send_staff_notification(request):
    id = request.POST.get('id')
    message = request.POST.get('message')
    school = getattr(request, 'school', None)
    qs = Staff.objects.filter(admin__school=school) if school else Staff.objects.all()
    staff = get_object_or_404(qs, admin_id=id)
    try:
        url = "https://fcm.googleapis.com/fcm/send"
        body = {
            'notification': {
                'title': "Student Management System",
                'body': message,
                'click_action': reverse('staff_view_notification'),
                'icon': static('dist/img/AdminLTELogo.png')
            },
            'to': staff.admin.fcm_token
        }
        headers = {'Authorization':
                   'key=AAAA3Bm8j_M:APA91bElZlOLetwV696SoEtgzpJr2qbxBfxVBfDWFiopBWzfCfzQp2nRyC7_A2mlukZEHV4g1AmyC6P_HonvSkY2YyliKt5tT3fe_1lrKod2Daigzhb2xnYQMxUWjCAIQcUexAMPZePB',
                   'Content-Type': 'application/json'}
        data = requests.post(url, data=json.dumps(body), headers=headers)
        notification = NotificationStaff(staff=staff, message=message)
        notification.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def delete_staff(request, staff_id):
    school = getattr(request, 'school', None)
    qs = CustomUser.objects.filter(school=school) if school else CustomUser.objects.all()
    staff = get_object_or_404(qs, staff__id=staff_id)
    staff.delete()
    messages.success(request, "Staff deleted successfully!")
    return redirect(reverse('manage_staff'))


def delete_student(request, student_id):
    school = getattr(request, 'school', None)
    qs = CustomUser.objects.filter(school=school) if school else CustomUser.objects.all()
    student = get_object_or_404(qs, student__id=student_id)
    student.delete()
    messages.success(request, "Student deleted successfully!")
    return redirect(reverse('manage_student'))


def delete_course(request, course_id):
    school = getattr(request, 'school', None)
    qs = Course.objects.filter(school=school) if school else Course.objects.all()
    course = get_object_or_404(qs, id=course_id)
    try:
        course.delete()
        messages.success(request, "Class deleted successfully!")
    except Exception:
        messages.error(
            request, "Sorry, some students are assigned to this class already. Kindly change the affected student class and try again")
    return redirect(reverse('manage_course'))


def delete_subject(request, subject_id):
    school = getattr(request, 'school', None)
    qs = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
    subject = get_object_or_404(qs, id=subject_id)
    course_id = subject.course_id
    subject.delete()
    messages.success(request, "Subject deleted successfully!")
    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)
    if course_id:
        return redirect(reverse('edit_class', args=[course_id]))
    return redirect(reverse('manage_subject'))


def delete_session(request, session_id):
    school = getattr(request, 'school', None)
    qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session = get_object_or_404(qs, id=session_id)
    try:
        session.delete()
        messages.success(request, "Session deleted successfully!")
    except Exception:
        messages.error(
            request, "There are students assigned to this session. Please move them to another session.")
    return redirect(reverse('manage_session'))


def admin_view_result(request):
    """Admin can view all student results (school-scoped)"""
    school = getattr(request, 'school', None)
    courses = Course.objects.filter(school=school) if school else Course.objects.all()
    subjects = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
    context = {
        'page_title': 'View Student Results',
        'courses': courses,
        'subjects': subjects
    }
    return render(request, 'hod_template/admin_view_result.html', context)


@csrf_exempt
def admin_get_students_for_result(request):
    """Fetch students by course and subject for admin (school-scoped)"""
    school = getattr(request, 'school', None)
    try:
        course_id = request.POST.get('course_id')
        subject_id = request.POST.get('subject_id')
        
        if course_id and subject_id:
            students = Student.objects.filter(course_id=course_id)
            if school:
                students = students.filter(admin__school=school)
            subject_qs = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
            subject = get_object_or_404(subject_qs, id=subject_id)
            
            student_result_data = []
            for student in students:
                try:
                    result = StudentResult.objects.get(student=student, subject=subject)
                    data = {
                        'student_id': student.id,
                        'student_name': student.admin.last_name + " " + student.admin.first_name,
                        'test': result.test,
                        'exam': result.exam,
                        'total': result.test + result.exam
                    }
                except StudentResult.DoesNotExist:
                    data = {
                        'student_id': student.id,
                        'student_name': student.admin.last_name + " " + student.admin.first_name,
                        'test': 0,
                        'exam': 0,
                        'total': 0
                    }
                student_result_data.append(data)
            
            return JsonResponse(student_result_data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def admin_edit_result(request):
    """Only superuser and staff can edit student results"""
    # Restrict to superuser only - regular admins cannot edit results
    if not request.user.is_superuser:
        messages.error(request, "Only super admin and staff can edit student results")
        return redirect('admin_home')
    
    school = getattr(request, 'school', None)
    subjects = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
    courses = Course.objects.filter(school=school) if school else Course.objects.all()
    students = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    context = {
        'page_title': 'Edit Student Results',
        'subjects': subjects,
        'courses': courses,
        'students': students
    }
    
    if request.method == 'POST':
        try:
            student_id = request.POST.get('student_id')
            subject_id = request.POST.get('subject_id')
            test = request.POST.get('test')
            exam = request.POST.get('exam')
            
            student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
            subject_qs = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
            student = get_object_or_404(student_qs, id=student_id)
            subject = get_object_or_404(subject_qs, id=subject_id)
            
            try:
                result = StudentResult.objects.get(student=student, subject=subject)
                result.test = test
                result.exam = exam
                result.save()
                messages.success(request, "Result Updated Successfully")
            except StudentResult.DoesNotExist:
                result = StudentResult(student=student, subject=subject, test=test, exam=exam)
                result.save()
                messages.success(request, "Result Added Successfully")
            
            return redirect(reverse('admin_edit_result'))
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return render(request, 'hod_template/admin_edit_result.html', context)


@csrf_exempt
def admin_fetch_student_result(request):
    """Fetch specific student result for admin (school-scoped)"""
    school = getattr(request, 'school', None)
    try:
        subject_id = request.POST.get('subject_id')
        student_id = request.POST.get('student_id')
        
        student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
        subject_qs = Subject.objects.filter(course__school=school) if school else Subject.objects.all()
        student = get_object_or_404(student_qs, id=student_id)
        subject = get_object_or_404(subject_qs, id=subject_id)
        
        result = StudentResult.objects.get(student=student, subject=subject)
        result_data = {
            'exam': result.exam,
            'test': result.test,
            'student_name': student.admin.last_name + " " + student.admin.first_name
        }
        return JsonResponse(result_data)
    except StudentResult.DoesNotExist:
        return JsonResponse({
            'exam': 0,
            'test': 0,
            'student_name': student.admin.last_name + " " + student.admin.first_name
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def admin_view_transcript(request):
    """Display student report cards (KNEC format) - select term and class"""
    from .report_card_views import _build_report_card_context
    from django.db.models import Q

    school = getattr(request, 'school', None)
    if not school:
        context = {
            'report_cards': [],
            'academic_terms': [],
            'courses': [],
            'page_title': 'Student Report Cards',
            'REPORTLAB_AVAILABLE': REPORTLAB_AVAILABLE,
            'selected_term': None,
            'selected_class': None,
            'term_id': None,
            'class_id': None,
            'no_school': True,
        }
        return render(request, 'hod_template/admin_view_transcript.html', context)

    academic_terms = AcademicTerm.objects.filter(school=school).order_by('-academic_year', 'term_name')
    courses = Course.objects.filter(school=school, is_active=True).order_by('name')

    term_id = request.GET.get('term')
    class_id = request.GET.get('course') or request.GET.get('class')

    report_cards = []
    selected_term = None
    selected_class = None

    if term_id and class_id:
        selected_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
        selected_class = get_object_or_404(Course, id=class_id, school=school)
        enrollments = StudentClassEnrollment.objects.filter(
            school_class=selected_class,
            status='active',
            student__admin__school=school
        ).filter(
            Q(term=selected_term) | Q(academic_year__academic_year=selected_term.academic_year)
        ).select_related('student__admin')
        for enr in enrollments:
            ctx = _build_report_card_context(enr.student, selected_term, school)
            ctx['serial_number'] = hashlib.md5(f"{enr.student.id}{enr.student.admin.username}".encode()).hexdigest()[:8].upper()
            report_cards.append(ctx)

    context = {
        'report_cards': report_cards,
        'academic_terms': academic_terms,
        'courses': courses,
        'page_title': 'Student Report Cards',
        'REPORTLAB_AVAILABLE': REPORTLAB_AVAILABLE,
        'selected_term': selected_term,
        'selected_class': selected_class,
        'term_id': term_id,
        'class_id': class_id,
        'no_school': False,
    }
    return render(request, 'hod_template/admin_view_transcript.html', context)


def admin_get_student_transcript(request):
    """Get detailed transcript for a specific student (school-scoped)"""
    school = getattr(request, 'school', None)
    try:
        student_id = request.POST.get('student_id')
        student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
        student = get_object_or_404(student_qs, id=student_id)
        
        results = StudentResult.objects.filter(student=student).select_related('subject')
        
        # Generate serial number (using student ID and timestamp)
        serial_hash = hashlib.md5(f"{student.id}{student.admin.username}".encode()).hexdigest()[:8].upper()
        serial_number = f"100{serial_hash}"
        
        transcript_data = {
            'serial_number': serial_number,
            'student_name': f"{student.admin.last_name}, {student.admin.first_name}",
            'reg_number': student.admin.username,
            'admission_number': student.admission_number if student.admission_number else student.admin.username,
            'course': student.course.name if student.course else 'N/A',
            'session': str(student.session) if student.session else 'N/A',
            'results': []
        }
        
        total_marks = 0
        total_subjects = 0
        passed_subjects = 0
        
        for result in results:
            total = result.test + result.exam
            total_marks += total
            total_subjects += 1
            
            # Calculate attendance percentage for this subject
            attendance_records = Attendance.objects.filter(subject=result.subject)
            if attendance_records.exists():
                attendance_reports = AttendanceReport.objects.filter(
                    student=student,
                    attendance__in=attendance_records
                )
                total_attendance = attendance_reports.count()
                present_count = attendance_reports.filter(status=True).count()
                if total_attendance > 0:
                    attendance_percentage = round((present_count / total_attendance) * 100)
                else:
                    attendance_percentage = 0
            else:
                attendance_percentage = 0
            
            # Calculate grade
            if total >= 70:
                grade = 'A'
            elif total >= 60:
                grade = 'B'
            elif total >= 50:
                grade = 'C'
            elif total >= 40:
                grade = 'D'
            else:
                grade = 'F'
            
            if total >= 40:  # Pass mark
                passed_subjects += 1
            
            # Generate unit code (using first letters of subject name)
            subject_code = ''.join([word[0].upper() for word in result.subject.name.split()[:3]])[:6]
            if len(subject_code) < 3:
                subject_code = result.subject.name[:6].upper().replace(' ', '')
            
            transcript_data['results'].append({
                'unit_code': subject_code,
                'subject': result.subject.name,
                'attendance': attendance_percentage,
                'test': result.test,
                'exam': result.exam,
                'total': total,
                'grade': grade
            })
        
        # Calculate GPA (average)
        if total_subjects > 0:
            transcript_data['average'] = round(total_marks / total_subjects, 2)
            transcript_data['total_marks'] = total_marks
            transcript_data['passed_subjects'] = passed_subjects
        else:
            transcript_data['average'] = 0
            transcript_data['total_marks'] = 0
            transcript_data['passed_subjects'] = 0
        
        return JsonResponse(transcript_data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def admin_download_transcript_pdf(request, student_id):
    """Generate and download PDF transcript for a student"""
    if not request.user.is_authenticated or int(request.user.user_type) not in [1, 2]:
        return redirect('login_page')
    
    if not REPORTLAB_AVAILABLE:
        messages.error(request, 'PDF generation is not available. Please install reportlab by running: pip install reportlab. Then restart your Django server.')
        return redirect('admin_view_transcript')
    
    school = getattr(request, 'school', None)
    student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    try:
        student = get_object_or_404(student_qs, id=student_id)
        results = StudentResult.objects.filter(student=student).select_related('subject')
        
        # Create response with PDF content type
        response = HttpResponse(content_type='application/pdf')
        filename = f"Transcript_{student.admin.username}_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Create PDF document
        doc = SimpleDocTemplate(response, pagesize=A4)
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        normal_style = styles['Normal']
        normal_style.fontSize = 11
        
        # Generate serial number
        serial_hash = hashlib.md5(f"{student.id}{student.admin.username}".encode()).hexdigest()[:8].upper()
        serial_number = f"100{serial_hash}"
        
        # Serial number in top right
        serial_para = Paragraph(f'<para alignment="right" fontSize="12" textColor="red"><b>{serial_number}</b></para>', normal_style)
        story.append(serial_para)
        story.append(Spacer(1, 0.1*inch))
        
        # Add school logo
        logo_path = os.path.join(settings.BASE_DIR, 'main_app', 'static', 'dist', 'img', 'cmsl.png')
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=1.2*inch, height=1.2*inch)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 0.15*inch))
        
        # Add title - Mount Kenya University style
        school_name = Paragraph("<b>SCHOOL MANAGEMENT SYSTEM</b>", ParagraphStyle('SchoolName', parent=normal_style, fontSize=18, alignment=TA_CENTER, fontName='Helvetica-Bold'))
        story.append(school_name)
        story.append(Spacer(1, 0.1*inch))
        
        office_text = Paragraph("OFFICE OF THE REGISTRAR ACADEMIC AFFAIRS", ParagraphStyle('Office', parent=normal_style, fontSize=11, alignment=TA_CENTER, fontName='Helvetica'))
        story.append(office_text)
        story.append(Spacer(1, 0.1*inch))
        
        transcript_title = Paragraph("<b>ACADEMIC TRANSCRIPT</b>", ParagraphStyle('Title', parent=normal_style, fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold'))
        story.append(transcript_title)
        story.append(Spacer(1, 0.3*inch))
        
        # Student information table - Mount Kenya University format
        student_info_data = [
            ['Name of Student:', f"{student.admin.last_name}, {student.admin.first_name}"],
            ['Reg No:', student.admin.username],
            ['Faculty/School:', student.course.name if student.course else 'N/A'],
            ['Department:', student.course.name if student.course else 'N/A'],
            ['Class:', student.course.name if student.course else 'N/A'],
            ['Programme:', student.course.name if student.course else 'N/A'],
            ['Academic Year:', str(student.session) if student.session else 'N/A'],
        ]
        
        student_info_table = Table(student_info_data, colWidths=[2*inch, 4.5*inch])
        student_info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(student_info_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Results table - Mount Kenya University format
        if results:
            table_data = [['Unit Code', 'Unit Title', 'Attendance', 'Marks', 'Grade']]
            
            total_marks = 0
            total_subjects = 0
            passed_subjects = 0
            
            for result in results:
                total = result.test + result.exam
                total_marks += total
                total_subjects += 1
                
                # Calculate attendance
                attendance_records = Attendance.objects.filter(subject=result.subject)
                if attendance_records.exists():
                    attendance_reports = AttendanceReport.objects.filter(
                        student=student,
                        attendance__in=attendance_records
                    )
                    total_attendance = attendance_reports.count()
                    present_count = attendance_reports.filter(status=True).count()
                    if total_attendance > 0:
                        attendance_percentage = round((present_count / total_attendance) * 100)
                    else:
                        attendance_percentage = 0
                else:
                    attendance_percentage = 0
                
                # Calculate grade
                if total >= 70:
                    grade = 'A'
                elif total >= 60:
                    grade = 'B'
                elif total >= 50:
                    grade = 'C'
                elif total >= 40:
                    grade = 'D'
                else:
                    grade = 'F'
                
                if total >= 40:
                    passed_subjects += 1
                
                # Generate unit code
                subject_code = ''.join([word[0].upper() for word in result.subject.name.split()[:3]])[:6]
                if len(subject_code) < 3:
                    subject_code = result.subject.name[:6].upper().replace(' ', '')
                
                table_data.append([
                    subject_code,
                    result.subject.name,
                    str(attendance_percentage),
                    str(total),
                    grade
                ])
            
            # Add summary rows
            average = round(total_marks / total_subjects, 2) if total_subjects > 0 else 0
            table_data.append(['', 'TOTAL:', '', str(total_marks), ''])
            table_data.append(['', 'AVERAGE:', '', str(average), ''])
            table_data.append(['', 'PASS:', '', '', str(passed_subjects)])
            
            results_table = Table(table_data, colWidths=[1*inch, 3*inch, 0.8*inch, 0.8*inch, 0.8*inch])
            results_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
                ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BACKGROUND', (0, 1), (-1, -4), colors.white),
                ('BACKGROUND', (0, -3), (-1, -1), colors.HexColor('#e0e0e0')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -4), [colors.white, colors.HexColor('#f9f9f9')]),
            ]))
            story.append(results_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Recommendation section
            recommendation_text = "PASS: RECOMMENDED TO PROCEED TO NEXT LEVEL" if average >= 50 else "FAIL: STUDENT MUST REPEAT THE COURSE"
            rec_style = ParagraphStyle('Recommendation', parent=normal_style, fontSize=10, alignment=TA_LEFT, fontName='Helvetica')
            rec_box = Table([['RECOMMENDATION'], [recommendation_text]], colWidths=[6.6*inch])
            rec_box.setStyle(TableStyle([
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (0, 1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(rec_box)
            story.append(Spacer(1, 0.3*inch))
            
            # Key to Grading System
            grading_data = [
                ['KEY TO GRADING SYSTEM:'],
                ['A: 70-100 (Excellent)', 'B: 60-69 (Good)', 'C: 50-59 (Credit)'],
                ['D: 40-49 (Pass)', 'F: 0-39 (Fail)', 'I: Incomplete'],
                ['X: Absent', 'P: Pass', 'W: Withdrawn'],
            ]
            grading_table = Table(grading_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
            grading_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f9f9f9')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ddd')),
            ]))
            story.append(grading_table)
        else:
            no_results = Paragraph("No results available for this student.", normal_style)
            story.append(no_results)
        
        story.append(Spacer(1, 0.4*inch))
        
        # Footer with signature and date - Mount Kenya University format
        story.append(Spacer(1, 0.2*inch))
        
        # Format date like "Fri 10th Jan 2020 10:30:00"
        day = datetime.now().day
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day % 10 - 1]
        date_str = datetime.now().strftime(f'%a %d{suffix} %b %Y %H:%M:%S')
        
        footer_left_data = [
            ['REGISTRAR (ACADEMIC AFFAIRS)'],
            ['SCHOOL MANAGEMENT SYSTEM'],
            ['', ''],  # Space for signature
            ['', ''],  # Space for signature
            ['Signature']
        ]
        
        footer_left_table = Table(footer_left_data, colWidths=[3.3*inch])
        footer_left_table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 3), (0, 3), 1, colors.black),  # Signature line
        ]))
        
        footer_right = Paragraph(
            f"<para fontSize='9'><b>Date of Issue:</b><br/>{date_str}</para>",
            ParagraphStyle('FooterRight', parent=normal_style, fontSize=9, alignment=TA_RIGHT)
        )
        
        footer_table = Table([[footer_left_table, footer_right]], colWidths=[3.3*inch, 3.3*inch])
        footer_table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(footer_table)
        
        # Signature line
        sig_line = Table([['', '']], colWidths=[3.3*inch, 3.3*inch])
        sig_line.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (0, 0), 1, colors.black),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ]))
        story.append(sig_line)
        sig_text = Paragraph("Signature", ParagraphStyle('Sig', parent=normal_style, fontSize=8, alignment=TA_LEFT))
        story.append(sig_text)
        
        # Build PDF
        doc.build(story)
        return response
        
    except Exception as e:
        messages.error(request, f'Error generating PDF: {str(e)}')
        return redirect('admin_view_transcript')


@csrf_exempt
def send_results_sms(request, student_id):
    """Send student results via SMS/STK push"""
    if not request.user.is_authenticated or int(request.user.user_type) not in [1, 2]:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    try:
        student = get_object_or_404(qs, id=student_id)
        
        # Check if student has phone number
        if not student.admin.phone_number:
            return JsonResponse({
                'success': False, 
                'error': f'Student {student.admin.first_name} {student.admin.last_name} does not have a phone number registered. Please update their profile.'
            })
        
        # Get student results
        results = StudentResult.objects.filter(student=student).select_related('subject')
        
        if not results.exists():
            return JsonResponse({
                'success': False,
                'error': f'No results found for {student.admin.first_name} {student.admin.last_name}'
            })
        
        # Format results message
        message = format_results_message(student, results)
        
        # Send SMS
        phone_number = student.admin.phone_number
        sms_result = send_sms(phone_number, message)
        
        if sms_result['success']:
            # Log notification
            notification = NotificationStudent(
                student=student,
                message=f"Results sent via SMS to {phone_number}"
            )
            notification.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Results sent successfully to {phone_number}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': sms_result.get('error', 'Failed to send SMS')
            })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error sending SMS: {str(e)}'
        })


@csrf_exempt
def send_all_results_sms(request):
    """Send results via SMS to all students (school-scoped)"""
    if not request.user.is_authenticated or int(request.user.user_type) not in [1, 2]:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    school = getattr(request, 'school', None)
    try:
        students = Student.objects.filter(admin__school=school) if school else Student.objects.all()
        success_count = 0
        error_count = 0
        errors = []
        
        for student in students:
            # Skip if no phone number
            if not student.admin.phone_number:
                error_count += 1
                errors.append(f"{student.admin.first_name} {student.admin.last_name}: No phone number")
                continue
            
            # Get results
            results = StudentResult.objects.filter(student=student).select_related('subject')
            
            if not results.exists():
                error_count += 1
                errors.append(f"{student.admin.first_name} {student.admin.last_name}: No results")
                continue
            
            # Format and send
            message = format_results_message(student, results)
            phone_number = student.admin.phone_number
            sms_result = send_sms(phone_number, message)
            
            if sms_result['success']:
                success_count += 1
                # Log notification
                notification = NotificationStudent(
                    student=student,
                    message=f"Results sent via SMS to {phone_number}"
                )
                notification.save()
            else:
                error_count += 1
                errors.append(f"{student.admin.first_name} {student.admin.last_name}: {sms_result.get('error', 'SMS failed')}")
        
        return JsonResponse({
            'success': True,
            'message': f'Sent to {success_count} students. {error_count} failed.',
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors[:10]  # Limit errors shown
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error sending SMS: {str(e)}'
        })


def admin_view_fees(request):
    """View and manage student fees"""
    # School Admin (user_type=1) and superuser have full access
    if not request.user.is_superuser and str(request.user.user_type) != '1':
        try:
            perm = AdminPermission.objects.get(admin=request.user)
            if not perm.can_view_fees:
                messages.error(request, "You don't have permission to view fees")
                return redirect('admin_home')
        except AdminPermission.DoesNotExist:
            messages.error(request, "You don't have permission to view fees")
            return redirect('admin_home')
    
    school = getattr(request, 'school', None)
    students = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    sessions = Session.objects.filter(school=school) if school else Session.objects.all()
    context = {
        'students': students,
        'sessions': sessions,
        'page_title': 'Student Fees Management'
    }
    return render(request, 'hod_template/admin_view_fees.html', context)


def admin_post_fees(request):
    """Post/Create fees for students"""
    if not request.user.is_superuser and str(request.user.user_type) != '1':
        try:
            perm = AdminPermission.objects.get(admin=request.user)
            if not perm.can_manage_fees:
                return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
        except AdminPermission.DoesNotExist:
            return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
    
    if request.method == 'POST':
        school = getattr(request, 'school', None)
        try:
            student_id = request.POST.get('student_id')
            session_id = request.POST.get('session_id')
            amount = float(request.POST.get('amount'))
            due_date = request.POST.get('due_date')
            notes = request.POST.get('notes', '')
            
            student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
            session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
            student = get_object_or_404(student_qs, id=student_id)
            session = get_object_or_404(session_qs, id=session_id)
            
            # Check if fees already exist for this student and session
            try:
                fees = StudentFees.objects.get(student=student, session=session)
                fees.amount_due = amount
                fees.due_date = due_date
                fees.notes = notes
                fees.save()
                messages.success(request, "Fees updated successfully")
            except StudentFees.DoesNotExist:
                fees = StudentFees.objects.create(
                    student=student,
                    session=session,
                    amount_due=amount,
                    due_date=due_date,
                    notes=notes
                )
                messages.success(request, "Fees posted successfully")
            
            return redirect('admin_view_fees')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect('admin_view_fees')


def admin_get_fees(request):
    """Fetch fees for a student via AJAX (school-scoped)"""
    school = getattr(request, 'school', None)
    try:
        student_id = request.POST.get('student_id')
        session_id = request.POST.get('session_id')
        
        student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
        session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
        student = get_object_or_404(student_qs, id=student_id)
        session = get_object_or_404(session_qs, id=session_id)
        
        try:
            fees = StudentFees.objects.get(student=student, session=session)
            fees_data = {
                'id': fees.id,
                'amount_due': float(fees.amount_due),
                'amount_paid': float(fees.amount_paid),
                'amount_outstanding': float(fees.amount_outstanding),
                'status': fees.status,
                'due_date': fees.due_date.strftime('%Y-%m-%d'),
                'payment_date': fees.payment_date.strftime('%Y-%m-%d') if fees.payment_date else '',
                'notes': fees.notes
            }
            return JsonResponse(fees_data)
        except StudentFees.DoesNotExist:
            return JsonResponse({'message': 'No fees found'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def admin_clear_fees(request):
    """Clear/Update fees payment"""
    if not request.user.is_superuser and str(request.user.user_type) != '1':
        try:
            perm = AdminPermission.objects.get(admin=request.user)
            if not perm.can_manage_fees:
                return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
        except AdminPermission.DoesNotExist:
            return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
    
    if request.method == 'POST':
        school = getattr(request, 'school', None)
        try:
            fees_id = request.POST.get('fees_id')
            amount_paid = Decimal(request.POST.get('amount_paid'))
            payment_date = request.POST.get('payment_date', datetime.now().date())
            
            fees_qs = StudentFees.objects.filter(student__admin__school=school) if school else StudentFees.objects.all()
            fees = get_object_or_404(fees_qs, id=fees_id)
            fees.amount_paid += amount_paid
            
            # Update status
            if fees.amount_paid >= fees.amount_due:
                fees.status = 'paid'
                fees.payment_date = payment_date
            elif fees.amount_paid > 0:
                fees.status = 'partial'
            
            fees.save()
            messages.success(request, "Payment recorded successfully")
            return redirect('admin_view_fees')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect('admin_view_fees')


def admin_manage_permissions(request):
    """Manage permissions for admins. Super admin: all admins. School admin: admins in their school."""
    school = getattr(request, 'school', None)
    if not request.user.is_superuser and str(request.user.user_type) != '1':
        messages.error(request, "Only admin can manage permissions")
        return redirect('admin_home')

    if request.user.is_superuser:
        admins = CustomUser.objects.filter(user_type=1).exclude(is_superuser=True)
    else:
        # School admin: only admins in their school
        admins = CustomUser.objects.filter(user_type=1, school=school).exclude(is_superuser=True) if school else CustomUser.objects.none()
    context = {
        'admins': admins,
        'page_title': 'Manage Admin Permissions'
    }
    return render(request, 'hod_template/admin_manage_permissions.html', context)


def admin_update_permission(request):
    """Update admin permissions. Super admin: any admin. School admin: only admins in their school."""
    school = getattr(request, 'school', None)
    if not request.user.is_superuser and str(request.user.user_type) != '1':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if request.method == 'POST':
        try:
            admin_id = request.POST.get('admin_id')
            permission_type = request.POST.get('permission_type')
            value = request.POST.get('value').lower() == 'true'

            admin_user = get_object_or_404(CustomUser, id=admin_id)
            # School admin can only update admins in their school
            if not request.user.is_superuser and school and admin_user.school_id != school.id:
                return JsonResponse({'error': 'You can only manage permissions for admins in your school'}, status=403)
            perm = AdminPermission.objects.get(admin=admin_user)
            
            if permission_type == 'can_view_fees':
                perm.can_view_fees = value
            elif permission_type == 'can_manage_fees':
                perm.can_manage_fees = value
            elif permission_type == 'can_edit_results':
                perm.can_edit_results = value
            elif permission_type == 'can_view_results':
                perm.can_view_results = value
            elif permission_type == 'can_manage_students':
                perm.can_manage_students = value
            elif permission_type == 'can_manage_staff':
                perm.can_manage_staff = value
            
            perm.save()
            return JsonResponse({'success': True, 'message': 'Permission updated successfully'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


def superadmin_search_student_results(request):
    """Superadmin only: search student by admission number and view/edit results."""
    if not request.user.is_superuser:
        return redirect('login_page')
    
    q = request.GET.get('q', '').strip()
    student = None
    results = []
    subjects = []
    
    if q:
        # Search by admission number (exact match)
        student = Student.objects.filter(admission_number__iexact=q).select_related('admin', 'course', 'session').first()
        if student:
            results = StudentResult.objects.filter(student=student).select_related('subject')
            subjects = Subject.objects.all()
    
    context = {
        'student': student,
        'results': results,
        'subjects': subjects,
        'query': q,
        'page_title': 'Search Student Results (Superadmin)'
    }
    return render(request, 'hod_template/superadmin_search_results.html', context)


def superadmin_update_student_result(request):
    """Superadmin only: update/edit student result via AJAX."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            student_id = request.POST.get('student_id')
            subject_id = request.POST.get('subject_id')
            test = request.POST.get('test', 0)
            exam = request.POST.get('exam', 0)
            
            student = get_object_or_404(Student, id=student_id)
            subject = get_object_or_404(Subject, id=subject_id)
            
            try:
                test = float(test)
                exam = float(exam)
            except ValueError:
                return JsonResponse({'error': 'Invalid test or exam value'}, status=400)
            
            # Get or create result
            result, created = StudentResult.objects.get_or_create(
                student=student,
                subject=subject
            )
            
            result.test = test
            result.exam = exam
            result.save()
            
            total = test + exam
            # Calculate grade
            if total >= 70:
                grade = 'A'
            elif total >= 60:
                grade = 'B'
            elif total >= 50:
                grade = 'C'
            elif total >= 40:
                grade = 'D'
            else:
                grade = 'F'
            
            return JsonResponse({
                'success': True,
                'message': 'Result updated successfully',
                'total': total,
                'grade': grade
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)


# Section Management
def add_section(request):
    from .forms import SectionForm
    form = SectionForm(request.POST or None)
    context = {'form': form, 'page_title': 'Add Section'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Section added successfully!")
                return redirect(reverse('add_section'))
            except Exception as e:
                messages.error(request, f"Could not add section: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/add_section_template.html', context)


def manage_section(request):
    sections = Section.objects.all()
    context = {'sections': sections, 'page_title': 'Manage Sections'}
    return render(request, 'hod_template/manage_section.html', context)


def edit_section(request, section_id):
    from .forms import SectionForm
    section = get_object_or_404(Section, id=section_id)
    form = SectionForm(request.POST or None, instance=section)
    context = {'form': form, 'section_id': section_id, 'page_title': 'Edit Section'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Section updated successfully!")
                return redirect(reverse('manage_section'))
            except Exception as e:
                messages.error(request, f"Could not update section: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/edit_section_template.html', context)


def delete_section(request, section_id):
    section = get_object_or_404(Section, id=section_id)
    try:
        section.delete()
        messages.success(request, "Section deleted successfully!")
    except Exception as e:
        messages.error(request, f"Could not delete section: {str(e)}")
    return redirect(reverse('manage_section'))


# Parent Management
def add_parent(request):
    from .forms import ParentForm
    from django.core.files.storage import FileSystemStorage
    
    form = ParentForm(request.POST or None, request.FILES or None)
    students = Student.objects.all()
    context = {'form': form, 'students': students, 'page_title': 'Add Parent/Guardian'}
    
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password')
            phone_number = form.cleaned_data.get('phone_number')
            passport = request.FILES.get('profile_pic')
            children_ids = request.POST.getlist('children')
            
            try:
                with transaction.atomic():
                    passport_url = ''
                    if passport:
                        fs = FileSystemStorage()
                        filename = fs.save(passport.name, passport)
                        passport_url = fs.url(filename)
                    
                    user = CustomUser.objects.create_user(
                        email=email, password=password, user_type=4,
                        first_name=first_name, last_name=last_name,
                        profile_pic=passport_url, phone_number=phone_number
                    )
                    user.gender = gender
                    user.address = address
                    user.school = getattr(request, 'school', None)
                    user.save()
                    
                    # Create Parent record (required before linking children)
                    parent = Parent.objects.create(admin=user)
                    
                    # Link children
                    if children_ids:
                        for child_id in children_ids:
                            student = Student.objects.get(id=child_id)
                            parent.children.add(student)
                
                messages.success(request, "Parent added successfully!")
                return redirect(reverse('add_parent'))
            except Exception as e:
                messages.error(request, f"Could not add parent: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/add_parent_template.html', context)


def manage_parent(request):
    parents = Parent.objects.all().select_related('admin')
    context = {'parents': parents, 'page_title': 'Manage Parents/Guardians'}
    return render(request, 'hod_template/manage_parent.html', context)


def edit_parent(request, parent_id):
    from django.core.files.storage import FileSystemStorage
    
    parent = get_object_or_404(Parent, id=parent_id)
    students = Student.objects.all()
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        address = request.POST.get('address')
        email = request.POST.get('email')
        gender = request.POST.get('gender')
        phone_number = request.POST.get('phone_number')
        password = request.POST.get('password')
        passport = request.FILES.get('profile_pic')
        children_ids = request.POST.getlist('children')
        
        try:
            user = parent.admin
            user.first_name = first_name
            user.last_name = last_name
            user.address = address
            user.email = email
            user.gender = gender
            user.phone_number = phone_number
            
            if password:
                user.set_password(password)
            
            if passport:
                fs = FileSystemStorage()
                filename = fs.save(passport.name, passport)
                user.profile_pic = fs.url(filename)
            
            user.save()
            
            # Update children
            parent.children.clear()
            for child_id in children_ids:
                student = Student.objects.get(id=child_id)
                parent.children.add(student)
            
            messages.success(request, "Parent updated successfully!")
            return redirect(reverse('manage_parent'))
        except Exception as e:
            messages.error(request, f"Could not update parent: {str(e)}")
    
    context = {
        'parent': parent,
        'parent_id': parent_id,
        'students': students,
        'page_title': 'Edit Parent/Guardian'
    }
    return render(request, 'hod_template/edit_parent_template.html', context)


def delete_parent(request, parent_id):
    parent = get_object_or_404(Parent, id=parent_id)
    try:
        parent.admin.delete()
        messages.success(request, "Parent deleted successfully!")
    except Exception as e:
        messages.error(request, f"Could not delete parent: {str(e)}")
    return redirect(reverse('manage_parent'))


@csrf_exempt
def link_parent_child(request):
    if request.method == 'POST':
        parent_id = request.POST.get('parent_id')
        student_id = request.POST.get('student_id')
        action = request.POST.get('action', 'add')
        
        try:
            parent = Parent.objects.get(id=parent_id)
            student = Student.objects.get(id=student_id)
            
            if action == 'add':
                parent.children.add(student)
            else:
                parent.children.remove(student)
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


# Timetable Management
def add_timetable(request):
    from .forms import TimetableForm
    form = TimetableForm(request.POST or None)
    context = {'form': form, 'page_title': 'Add Timetable Entry'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                timetable = form.save(commit=False)
                timetable.staff = timetable.subject.staff
                timetable.save()
                messages.success(request, "Timetable entry added successfully!")
                return redirect(reverse('add_timetable'))
            except Exception as e:
                messages.error(request, f"Could not add timetable: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/add_timetable_template.html', context)


def manage_timetable(request):
    timetables = Timetable.objects.all().select_related('course', 'subject', 'staff__admin')
    courses = Course.objects.all()
    context = {
        'timetables': timetables,
        'courses': courses,
        'page_title': 'Manage Timetable'
    }
    return render(request, 'hod_template/manage_timetable.html', context)


def edit_timetable(request, timetable_id):
    from .forms import TimetableForm
    timetable = get_object_or_404(Timetable, id=timetable_id)
    form = TimetableForm(request.POST or None, instance=timetable)
    context = {'form': form, 'timetable_id': timetable_id, 'page_title': 'Edit Timetable Entry'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Timetable updated successfully!")
                return redirect(reverse('manage_timetable'))
            except Exception as e:
                messages.error(request, f"Could not update timetable: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/edit_timetable_template.html', context)


def delete_timetable(request, timetable_id):
    timetable = get_object_or_404(Timetable, id=timetable_id)
    try:
        timetable.delete()
        messages.success(request, "Timetable entry deleted successfully!")
    except Exception as e:
        messages.error(request, f"Could not delete timetable: {str(e)}")
    return redirect(reverse('manage_timetable'))


def view_class_timetable(request, class_id=None, course_id=None):
    school = getattr(request, 'school', None)
    cid = class_id or course_id
    course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
    course = get_object_or_404(course_qs, id=cid)
    timetables = Timetable.objects.filter(course=course).select_related(
        'subject', 'staff__admin'
    ).order_by('day', 'start_time')
    
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    timetable_by_day = {day: [] for day in days}
    for tt in timetables:
        if tt.day in timetable_by_day:
            timetable_by_day[tt.day].append(tt)
    
    context = {
        'course': course,
        'timetable_by_day': timetable_by_day,
        'days': days,
        'page_title': f'Timetable - {course.name}'
    }
    return render(request, 'hod_template/view_class_timetable.html', context)


# Announcement Management
def add_announcement(request):
    from .forms import AnnouncementForm
    form = AnnouncementForm(request.POST or None, request.FILES or None)
    context = {'form': form, 'page_title': 'Add Announcement'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                announcement = form.save(commit=False)
                announcement.created_by = request.user
                announcement.save()
                messages.success(request, "Announcement published successfully!")
                return redirect(reverse('manage_announcement'))
            except Exception as e:
                messages.error(request, f"Could not add announcement: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/add_announcement_template.html', context)


def manage_announcement(request):
    school = getattr(request, 'school', None)
    announcements = Announcement.objects.filter(created_by__school=school).select_related('created_by', 'target_course') if school else Announcement.objects.all().select_related('created_by', 'target_course')
    context = {'announcements': announcements, 'page_title': 'Manage Announcements'}
    return render(request, 'hod_template/manage_announcement.html', context)


def edit_announcement(request, announcement_id):
    from .forms import AnnouncementForm
    school = getattr(request, 'school', None)
    ann_qs = Announcement.objects.filter(created_by__school=school) if school else Announcement.objects.all()
    announcement = get_object_or_404(ann_qs, id=announcement_id)
    form = AnnouncementForm(request.POST or None, request.FILES or None, instance=announcement)
    context = {'form': form, 'announcement_id': announcement_id, 'page_title': 'Edit Announcement'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Announcement updated successfully!")
                return redirect(reverse('manage_announcement'))
            except Exception as e:
                messages.error(request, f"Could not update announcement: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/edit_announcement_template.html', context)


def delete_announcement(request, announcement_id):
    school = getattr(request, 'school', None)
    ann_qs = Announcement.objects.filter(created_by__school=school) if school else Announcement.objects.all()
    announcement = get_object_or_404(ann_qs, id=announcement_id)
    try:
        announcement.delete()
        messages.success(request, "Announcement deleted successfully!")
    except Exception as e:
        messages.error(request, f"Could not delete announcement: {str(e)}")
    return redirect(reverse('manage_announcement'))


# ============================================================
# KENYA CBC CLASS MANAGEMENT
# ============================================================

# Grade Level Management
def manage_grade_levels(request):
    """View all Kenya CBC grade levels - always ordered by Order Index ascending"""
    school = getattr(request, 'school', None)
    grade_levels = (GradeLevel.objects.filter(school=school) if school else GradeLevel.objects.all()).order_by('order_index')
    context = {
        'grade_levels': grade_levels,
        'page_title': 'Manage Grade Levels (Kenya CBC)'
    }
    return render(request, 'hod_template/manage_grade_levels.html', context)


def add_grade_level(request):
    """Add a new grade level - Code and Order Index auto-generated if empty"""
    from .forms import GradeLevelForm
    school = getattr(request, 'school', None)
    form = GradeLevelForm(request.POST or None, school=school)
    context = {'form': form, 'page_title': 'Add Grade Level'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                if school:
                    obj.school = school
                obj.save()
                messages.success(request, "Grade level added successfully!")
                return redirect(reverse('manage_grade_levels'))
            except Exception as e:
                messages.error(request, f"Could not add grade level: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/add_grade_level_template.html', context)


def edit_grade_level(request, grade_level_id):
    """Edit an existing grade level"""
    from .forms import GradeLevelForm
    school = getattr(request, 'school', None)
    qs = GradeLevel.objects.filter(school=school) if school else GradeLevel.objects.all()
    grade_level = get_object_or_404(qs, id=grade_level_id)
    form = GradeLevelForm(request.POST or None, instance=grade_level, school=school or grade_level.school)
    context = {'form': form, 'grade_level_id': grade_level_id, 'page_title': 'Edit Grade Level'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Grade level updated successfully!")
                return redirect(reverse('manage_grade_levels'))
            except Exception as e:
                messages.error(request, f"Could not update grade level: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/edit_grade_level_template.html', context)


def delete_grade_level(request, grade_level_id):
    """Delete a grade level"""
    school = getattr(request, 'school', None)
    qs = GradeLevel.objects.filter(school=school) if school else GradeLevel.objects.all()
    grade_level = get_object_or_404(qs, id=grade_level_id)
    try:
        grade_level.delete()
        messages.success(request, "Grade level deleted successfully!")
    except Exception as e:
        messages.error(request, f"Could not delete grade level: {str(e)}")
    return redirect(reverse('manage_grade_levels'))


# Stream Management
def manage_streams(request):
    """View all class streams"""
    school = getattr(request, 'school', None)
    streams = Stream.objects.filter(school=school) if school else Stream.objects.all()
    context = {
        'streams': streams,
        'page_title': 'Manage Streams'
    }
    return render(request, 'hod_template/manage_streams.html', context)


def add_stream(request):
    """Add a new stream"""
    from .forms import StreamForm
    school = getattr(request, 'school', None)
    form = StreamForm(request.POST or None)
    context = {'form': form, 'page_title': 'Add Stream'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                if school:
                    obj.school = school
                obj.save()
                messages.success(request, "Stream added successfully!")
                return redirect(reverse('manage_streams'))
            except Exception as e:
                messages.error(request, f"Could not add stream: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/add_stream_template.html', context)


def edit_stream(request, stream_id):
    """Edit an existing stream"""
    from .forms import StreamForm
    school = getattr(request, 'school', None)
    qs = Stream.objects.filter(school=school) if school else Stream.objects.all()
    stream = get_object_or_404(qs, id=stream_id)
    form = StreamForm(request.POST or None, instance=stream)
    context = {'form': form, 'stream_id': stream_id, 'page_title': 'Edit Stream'}
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Stream updated successfully!")
                return redirect(reverse('manage_streams'))
            except Exception as e:
                messages.error(request, f"Could not update stream: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    return render(request, 'hod_template/edit_stream_template.html', context)


def delete_stream(request, stream_id):
    """Delete a stream"""
    school = getattr(request, 'school', None)
    qs = Stream.objects.filter(school=school) if school else Stream.objects.all()
    stream = get_object_or_404(qs, id=stream_id)
    try:
        stream.delete()
        messages.success(request, "Stream deleted successfully!")
    except Exception as e:
        messages.error(request, f"Could not delete stream: {str(e)}")
    return redirect(reverse('manage_streams'))


# Class Management (Enhanced Course)
def manage_classes(request):
    """View all classes with CBC structure"""
    school = getattr(request, 'school', None)
    qs = Course.objects.filter(is_active=True)
    if school:
        qs = qs.filter(school=school)
    classes = qs.select_related(
        'grade_level', 'stream', 'class_teacher__admin', 'academic_year'
    )
    grade_levels = GradeLevel.objects.filter(school=school, is_active=True) if school else GradeLevel.objects.none()
    streams = Stream.objects.filter(school=school) if school else Stream.objects.none()
    
    context = {
        'classes': classes,
        'grade_levels': grade_levels,
        'streams': streams,
        'page_title': 'Manage Classes'
    }
    return render(request, 'hod_template/manage_classes.html', context)


def add_class(request):
    """Add a new class"""
    from .forms import CourseForm
    
    if request.method == 'POST':
        post_data = request.POST.copy()
        # Auto-generate name from grade_level + stream before validation
        grade_level_id = post_data.get('grade_level')
        stream_id = post_data.get('stream')
        if grade_level_id and stream_id:
            grade_level = GradeLevel.objects.filter(id=grade_level_id).first()
            stream = Stream.objects.filter(id=stream_id).first()
            if grade_level and stream:
                post_data['name'] = f"{grade_level.code} {stream.name}"
        # Remove empty optional FK fields so form uses default (None)
        for field in ('academic_year', 'class_teacher'):
            if post_data.get(field) == '':
                del post_data[field]
        form = CourseForm(post_data, school=getattr(request, 'school', None))
        if form.is_valid():
            try:
                school_class = form.save(commit=False)
                school_class.school = getattr(request, 'school', None)
                school_class.save()
                messages.success(request, "Class added successfully!")
                return redirect(reverse('manage_classes'))
            except Exception as e:
                messages.error(request, f"Could not add class: {str(e)}")
        else:
            for field_name, errors in form.errors.items():
                label = form.fields[field_name].label if field_name in form.fields else field_name
                for err in errors:
                    messages.error(request, f"{label}: {err}")
    else:
        form = CourseForm(school=getattr(request, 'school', None))
    
    school = getattr(request, 'school', None)
    context = {
        'form': form, 
        'page_title': 'Add Class',
        'grade_levels': GradeLevel.objects.filter(school=school, is_active=True) if school else GradeLevel.objects.none(),
        'streams': Stream.objects.filter(school=school) if school else Stream.objects.none(),
        'teachers': Staff.objects.filter(admin__school=school) if school else Staff.objects.none(),
        'sessions': Session.objects.filter(school=school) if school else Session.objects.none()
    }
    return render(request, 'hod_template/add_class_template.html', context)


def edit_class(request, class_id=None, course_id=None):
    """Edit an existing class (accepts class_id or course_id for URL compatibility)"""
    from .forms import CourseForm
    school = getattr(request, 'school', None)
    cid = class_id or course_id
    course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
    school_class = get_object_or_404(course_qs, id=cid)
    if school and school_class.school_id != school.id:
        messages.error(request, "You do not have permission to edit this class.")
        return redirect(reverse('manage_classes'))
    form = CourseForm(request.POST or None, instance=school_class, school=school)

    # Handle add subject (inline form)
    if request.method == 'POST' and request.POST.get('action') == 'add_subject':
        subj_name = request.POST.get('subject_name', '').strip()
        staff_id = request.POST.get('subject_teacher')
        if subj_name and staff_id:
            try:
                staff = Staff.objects.get(id=staff_id, admin__school=school) if school else Staff.objects.get(id=staff_id)
                Subject.objects.create(name=subj_name, staff=staff, course=school_class)
                messages.success(request, f"Subject '{subj_name}' added successfully!")
            except Staff.DoesNotExist:
                messages.error(request, "Invalid teacher selected.")
            except Exception as e:
                messages.error(request, f"Could not add subject: {str(e)}")
        else:
            messages.error(request, "Subject name and teacher are required.")
        return redirect(reverse('edit_class', args=[cid]))

    if request.method == 'POST' and request.POST.get('action') != 'add_subject':
        if form.is_valid():
            try:
                updated_class = form.save(commit=False)
                # Auto-generate name if grade_level and stream are selected
                if updated_class.grade_level and updated_class.stream:
                    updated_class.name = f"{updated_class.grade_level.code} {updated_class.stream.name}"
                updated_class.save()
                messages.success(request, "Class updated successfully!")
                return redirect(reverse('manage_classes'))
            except Exception as e:
                messages.error(request, f"Could not update class: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")

    class_subjects = Subject.objects.filter(course=school_class).select_related('staff__admin')

    context = {
        'form': form,
        'class_id': cid,
        'school_class': school_class,
        'class_subjects': class_subjects,
        'page_title': 'Edit Class',
        'grade_levels': GradeLevel.objects.filter(school=school, is_active=True) if school else GradeLevel.objects.none(),
        'streams': Stream.objects.filter(school=school) if school else Stream.objects.none(),
        'teachers': Staff.objects.filter(admin__school=school) if school else Staff.objects.none(),
        'sessions': Session.objects.filter(school=school) if school else Session.objects.none()
    }
    return render(request, 'hod_template/edit_class_template.html', context)


def delete_class(request, class_id=None, course_id=None):
    """Soft delete a class (accepts class_id or course_id for URL compatibility)"""
    school = getattr(request, 'school', None)
    cid = class_id or course_id
    course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
    school_class = get_object_or_404(course_qs, id=cid)
    if school and school_class.school_id != school.id:
        messages.error(request, "You do not have permission to delete this class.")
        return redirect(reverse('manage_classes'))
    try:
        school_class.is_active = False
        school_class.save()
        messages.success(request, "Class deactivated successfully!")
    except Exception as e:
        messages.error(request, f"Could not deactivate class: {str(e)}")
    return redirect(reverse('manage_classes'))


def view_class_students(request, class_id):
    """View students enrolled in a class"""
    school = getattr(request, 'school', None)
    course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
    school_class = get_object_or_404(course_qs, id=class_id)
    enrollments = StudentClassEnrollment.objects.filter(
        school_class=school_class,
        status='active'
    ).select_related('student__admin', 'academic_year')
    
    # Also get students directly assigned (backward compatibility)
    direct_students = Student.objects.filter(
        Q(course=school_class) | Q(current_class=school_class)
    ).select_related('admin')
    
    context = {
        'school_class': school_class,
        'enrollments': enrollments,
        'direct_students': direct_students,
        'page_title': f'Students in {school_class}'
    }
    return render(request, 'hod_template/view_class_students.html', context)


# Student Enrollment Management
def manage_enrollments(request):
    """View all student enrollments (school-scoped)"""
    school = getattr(request, 'school', None)
    enrollments = StudentClassEnrollment.objects.select_related(
        'student__admin', 'school_class__grade_level', 'school_class__stream', 'academic_year'
    )
    if school:
        enrollments = enrollments.filter(school_class__school=school)
    context = {
        'enrollments': enrollments,
        'page_title': 'Manage Student Enrollments'
    }
    return render(request, 'hod_template/manage_enrollments.html', context)


def add_enrollment(request):
    """MVP: Enroll student in class - auto-assigns subjects for Class+Stream+Term"""
    from .forms import StudentClassEnrollmentForm
    from .models import StudentSubjectEnrollment
    form = StudentClassEnrollmentForm(request.POST or None)
    active_term = AcademicTerm.get_active_term(school=getattr(request, 'school', None))
    
    if request.method == 'POST':
        if not active_term:
            messages.error(request, "No active term. Please activate an academic term before enrolling students.")
        elif active_term and active_term.is_locked:
            messages.error(request, "Term is closed. No new enrollments allowed.")
        elif form.is_valid():
            try:
                enrollment = form.save(commit=False)
                enrollment.term = active_term
                # Check if student already has an active enrollment for this academic year
                existing = StudentClassEnrollment.objects.filter(
                    student=enrollment.student,
                    academic_year=enrollment.academic_year,
                    status='active'
                ).first()
                
                if existing:
                    messages.error(request, f"Student already enrolled in {existing.school_class} for this academic year")
                else:
                    enrollment.save()
                    # Update student's current_class
                    enrollment.student.current_class = enrollment.school_class
                    enrollment.student.course = enrollment.school_class
                    enrollment.student.save()
                    # MVP: Auto-assign subjects for Class + Term
                    subjects = Subject.objects.filter(
                        course=enrollment.school_class
                    ).filter(
                        models.Q(term=active_term) | models.Q(term__isnull=True)
                    )
                    for subj in subjects:
                        StudentSubjectEnrollment.objects.get_or_create(
                            student=enrollment.student,
                            subject=subj,
                            term=active_term,
                            defaults={'enrollment': enrollment}
                        )
                    # Auto-bill: create FeeBalance for enrolled student
                    _create_fee_balance_for_enrollment(
                        enrollment.student,
                        enrollment.school_class,
                        enrollment.academic_year,
                        active_term
                    )
                    messages.success(request, f"Student enrolled! Auto-assigned {subjects.count()} subjects. Fee invoice generated.")
                    return redirect(reverse('manage_enrollments'))
            except Exception as e:
                messages.error(request, f"Could not enroll student: {str(e)}")
        else:
            messages.error(request, "Please fill form properly")
    
    school = getattr(request, 'school', None)
    students_qs = Student.objects.filter(admin__school=school).select_related('admin') if school else Student.objects.select_related('admin').all()
    classes_qs = Course.objects.filter(school=school, is_active=True) if school else Course.objects.filter(is_active=True)
    sessions_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    context = {
        'form': form,
        'students': students_qs,
        'classes': classes_qs,
        'sessions': sessions_qs,
        'active_term': active_term,
        'page_title': 'Enroll Student'
    }
    return render(request, 'hod_template/add_enrollment_template.html', context)


def bulk_enrollment(request):
    """Bulk enroll students in a class"""
    active_term = AcademicTerm.get_active_term(school=getattr(request, 'school', None))
    if request.method == 'POST':
        if not active_term:
            messages.error(request, "No active term. Please activate an academic term before enrolling students.")
        else:
            student_ids = request.POST.getlist('students')
            class_id = request.POST.get('school_class')
            academic_year_id = request.POST.get('academic_year')
            school = getattr(request, 'school', None)
            try:
                course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
                session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
                school_class = course_qs.get(id=class_id)
                academic_year = session_qs.get(id=academic_year_id)
                enrolled_count = 0
                skipped_count = 0
                student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
                for student_id in student_ids:
                    student = student_qs.get(id=student_id)
                    existing = StudentClassEnrollment.objects.filter(
                        student=student,
                        academic_year=academic_year,
                        status='active'
                    ).first()
                    if existing:
                        skipped_count += 1
                    else:
                        StudentClassEnrollment.objects.create(
                            student=student,
                            school_class=school_class,
                            academic_year=academic_year,
                            term=active_term,
                            status='active'
                        )
                        student.current_class = school_class
                        student.course = school_class
                        student.save()
                        # Auto-bill: create FeeBalance for each enrolled student
                        _create_fee_balance_for_enrollment(
                            student, school_class, academic_year, active_term
                        )
                        enrolled_count += 1
                messages.success(request, f"Enrolled {enrolled_count} students. Fee invoices generated. Skipped {skipped_count} (already enrolled)")
                return redirect(reverse('manage_enrollments'))
            except Exception as e:
                messages.error(request, f"Bulk enrollment failed: {str(e)}")
    
    school = getattr(request, 'school', None)
    students_qs = Student.objects.filter(admin__school=school).select_related('admin') if school else Student.objects.select_related('admin').all()
    classes_qs = Course.objects.filter(school=school, is_active=True).select_related('grade_level', 'stream') if school else Course.objects.filter(is_active=True).select_related('grade_level', 'stream')
    sessions_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    context = {
        'active_term': active_term,
        'students': students_qs,
        'classes': classes_qs,
        'sessions': sessions_qs,
        'page_title': 'Bulk Enrollment'
    }
    return render(request, 'hod_template/bulk_enrollment_template.html', context)


def transfer_student(request, enrollment_id):
    """Transfer a student to a different class (or stream)"""
    from .models import StudentSubjectEnrollment
    school = getattr(request, 'school', None)
    enrollment_qs = StudentClassEnrollment.objects.filter(school_class__school=school) if school else StudentClassEnrollment.objects.all()
    enrollment = get_object_or_404(enrollment_qs, id=enrollment_id)
    
    if request.method == 'POST':
        new_class_id = request.POST.get('new_class')
        notes = request.POST.get('notes', '')
        
        try:
            course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
            new_class = course_qs.get(id=new_class_id)
            active_term = AcademicTerm.get_active_term(school=getattr(request, 'school', None))
            if active_term and active_term.is_locked:
                messages.error(request, "Term is closed. Transfers not allowed.")
            else:
                # Mark old enrollment as transferred
                enrollment.status = 'transferred'
                enrollment.notes = notes
                enrollment.save()
                
                # Remove old subject enrollments (stream transfer: new subjects)
                StudentSubjectEnrollment.objects.filter(
                    student=enrollment.student,
                    term=active_term or enrollment.term
                ).delete()
                
                # Create new enrollment
                new_enrollment = StudentClassEnrollment.objects.create(
                    student=enrollment.student,
                    school_class=new_class,
                    academic_year=enrollment.academic_year,
                    term=active_term or enrollment.term,
                    status='active',
                    previous_enrollment=enrollment,
                    notes=f"Transferred from {enrollment.school_class}"
                )
                
                # MVP: Auto-assign new stream subjects
                term_obj = active_term or enrollment.term
                if term_obj:
                    subjects = Subject.objects.filter(
                        course=new_class
                    ).filter(
                        models.Q(term=term_obj) | models.Q(term__isnull=True)
                    )
                    for subj in subjects:
                        StudentSubjectEnrollment.objects.get_or_create(
                            student=enrollment.student,
                            subject=subj,
                            term=term_obj,
                            defaults={'enrollment': new_enrollment}
                        )
                
                # Update student's current class
                enrollment.student.current_class = new_class
                enrollment.student.course = new_class
                enrollment.student.save()
                
                # Auto-bill: update FeeBalance with new class fee structure
                _create_fee_balance_for_enrollment(
                    enrollment.student,
                    new_class,
                    enrollment.academic_year,
                    active_term or enrollment.term
                )
                
                messages.success(request, f"Student transferred to {new_class}. Subjects updated. Fee invoice updated.")
                return redirect(reverse('manage_enrollments'))
        except Exception as e:
            messages.error(request, f"Transfer failed: {str(e)}")
    
    # For stream transfer: show only same-grade classes (different stream)
    same_grade = enrollment.school_class.grade_level_id if enrollment.school_class else None
    base = Course.objects.filter(is_active=True)
    if school:
        base = base.filter(school=school)
    if same_grade:
        stream_classes = base.filter(grade_level_id=same_grade).exclude(id=enrollment.school_class.id).select_related('stream')
    else:
        stream_classes = base.exclude(id=enrollment.school_class.id)
    
    context = {
        'enrollment': enrollment,
        'classes': stream_classes,
        'page_title': f'Transfer Student: {enrollment.student}'
    }
    return render(request, 'hod_template/transfer_student_template.html', context)


# Promotion Management
def promotion_dashboard(request):
    """Dashboard for student promotions (school-scoped)"""
    school = getattr(request, 'school', None)
    sessions = Session.objects.filter(school=school).order_by('-start_year') if school else Session.objects.all().order_by('-start_year')
    grade_levels = GradeLevel.objects.filter(school=school, is_active=True) if school else GradeLevel.objects.filter(is_active=True)
    classes = Course.objects.filter(school=school, is_active=True).select_related('grade_level', 'stream') if school else Course.objects.filter(is_active=True).select_related('grade_level', 'stream')
    recent_promotions = PromotionRecord.objects.filter(from_academic_year__school=school)[:10] if school else PromotionRecord.objects.all()[:10]
    
    context = {
        'sessions': sessions,
        'grade_levels': grade_levels,
        'classes': classes,
        'recent_promotions': recent_promotions,
        'page_title': 'Student Promotion'
    }
    return render(request, 'hod_template/promotion_dashboard.html', context)


def bulk_promote(request):
    """Bulk promote students from one class to the next"""
    if request.method == 'POST':
        from_class_id = request.POST.get('from_class')
        to_class_id = request.POST.get('to_class')
        from_year_id = request.POST.get('from_academic_year')
        to_year_id = request.POST.get('to_academic_year')
        student_ids = request.POST.getlist('students')
        
        school = getattr(request, 'school', None)
        try:
            course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
            session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
            from_class = course_qs.get(id=from_class_id)
            to_class = course_qs.get(id=to_class_id)
            from_year = session_qs.get(id=from_year_id)
            to_year = session_qs.get(id=to_year_id)
            
            # Create promotion record
            promotion_record = PromotionRecord.objects.create(
                from_academic_year=from_year,
                to_academic_year=to_year,
                from_class=from_class,
                to_class=to_class,
                promoted_by=request.user,
                status='processing'
            )
            
            promoted_count = 0
            failed_count = 0
            
            # Get students to promote (school-scoped)
            if student_ids:
                students_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
                students = students_qs.filter(id__in=student_ids)
            else:
                # Promote all active students in the class
                enrollments = StudentClassEnrollment.objects.filter(
                    school_class=from_class,
                    academic_year=from_year,
                    status='active'
                )
                students = [e.student for e in enrollments]
            
            for student in students:
                try:
                    # Mark old enrollment as promoted
                    old_enrollment = StudentClassEnrollment.objects.filter(
                        student=student,
                        school_class=from_class,
                        academic_year=from_year,
                        status='active'
                    ).first()
                    
                    if old_enrollment:
                        old_enrollment.status = 'promoted'
                        old_enrollment.save()
                    
                    # Create new enrollment
                    new_enrollment = StudentClassEnrollment.objects.create(
                        student=student,
                        school_class=to_class,
                        academic_year=to_year,
                        status='active',
                        promoted_from=old_enrollment
                    )
                    
                    # Update student's current class
                    student.current_class = to_class
                    student.course = to_class
                    student.session = to_year
                    student.save()
                    
                    # Auto-bill: create FeeBalance for new session/class
                    _create_fee_balance_for_enrollment(student, to_class, to_year, None)
                    
                    promoted_count += 1
                except Exception as e:
                    failed_count += 1
            
            # Update promotion record
            promotion_record.students_promoted = promoted_count
            promotion_record.students_failed = failed_count
            promotion_record.status = 'completed'
            promotion_record.completed_at = datetime.now()
            promotion_record.save()
            
            messages.success(request, f"Promoted {promoted_count} students from {from_class} to {to_class}")
            return redirect(reverse('promotion_dashboard'))
            
        except Exception as e:
            messages.error(request, f"Promotion failed: {str(e)}")
    
    school = getattr(request, 'school', None)
    classes_qs = Course.objects.filter(school=school, is_active=True).select_related('grade_level', 'stream') if school else Course.objects.filter(is_active=True).select_related('grade_level', 'stream')
    sessions_qs = Session.objects.filter(school=school).order_by('-start_year') if school else Session.objects.all().order_by('-start_year')
    context = {
        'classes': classes_qs,
        'sessions': sessions_qs,
        'page_title': 'Bulk Promotion'
    }
    return render(request, 'hod_template/bulk_promote_template.html', context)


@csrf_exempt
def get_class_students(request):
    """AJAX endpoint to get students in a class for a specific academic year (school-scoped)"""
    class_id = request.GET.get('class_id')
    academic_year_id = request.GET.get('academic_year_id')
    school = getattr(request, 'school', None)
    
    try:
        base = StudentClassEnrollment.objects.filter(
            school_class_id=class_id,
            academic_year_id=academic_year_id,
            status='active'
        )
        if school:
            base = base.filter(school_class__school=school)
        enrollments = base.select_related('student__admin')
        
        students = []
        for enrollment in enrollments:
            students.append({
                'id': enrollment.student.id,
                'name': str(enrollment.student),
                'admission_number': enrollment.student.admission_number
            })
        
        # Also include students directly assigned (backward compatibility)
        direct_qs = Student.objects.filter(course_id=class_id)
        if school:
            direct_qs = direct_qs.filter(admin__school=school)
        direct_students = direct_qs.select_related('admin')
        for student in direct_students:
            if not any(s['id'] == student.id for s in students):
                students.append({
                    'id': student.id,
                    'name': str(student),
                    'admission_number': student.admission_number
                })
        
        return JsonResponse({'success': True, 'students': students})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
def get_next_grade_class(request):
    """AJAX endpoint to get suggested next class based on grade progression (school-scoped)"""
    current_class_id = request.GET.get('class_id')
    school = getattr(request, 'school', None)
    
    try:
        course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
        current_class = course_qs.get(id=current_class_id)
        
        if current_class.grade_level:
            next_grade = current_class.grade_level.get_next_grade()
            
            if next_grade:
                # Find a class with the same stream in the next grade
                suggested_qs = Course.objects.filter(
                    grade_level=next_grade,
                    stream=current_class.stream,
                    is_active=True
                )
                if school:
                    suggested_qs = suggested_qs.filter(school=school)
                suggested_class = suggested_qs.first()
                
                if suggested_class:
                    return JsonResponse({
                        'success': True,
                        'suggested_class': {
                            'id': suggested_class.id,
                            'name': str(suggested_class)
                        }
                    })
        
        return JsonResponse({'success': True, 'suggested_class': None})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def promotion_history(request):
    """View promotion history (school-scoped)"""
    school = getattr(request, 'school', None)
    base = PromotionRecord.objects.select_related(
        'from_academic_year', 'to_academic_year', 'from_class', 'to_class', 'promoted_by'
    )
    promotions = base.filter(from_academic_year__school=school) if school else base
    context = {
        'promotions': promotions,
        'page_title': 'Promotion History'
    }
    return render(request, 'hod_template/promotion_history.html', context)


# ============================================
# BULK SMS VIEWS
# ============================================

def bulk_sms(request):
    """Bulk SMS composition and sending (school-scoped)"""
    school = getattr(request, 'school', None)
    if request.method == 'POST':
        recipient_type = request.POST.get('recipient_type')
        message = request.POST.get('message')
        course_id = request.POST.get('course')
        grade_level_id = request.POST.get('grade_level')
        custom_numbers = request.POST.get('custom_numbers', '')
        schedule_time = request.POST.get('schedule_time')
        
        try:
            batch_id = str(uuid.uuid4())[:8]
            queued = 0
            errors = []
            
            if recipient_type == 'all_students':
                students = Student.objects.filter(admin__school=school) if school else Student.objects.all()
                result = send_bulk_sms_to_students(students, message, created_by=request.user)
                queued = result['queued']
                errors = result['errors']
                
            elif recipient_type == 'all_parents':
                students = Student.objects.filter(admin__school=school) if school else Student.objects.all()
                result = send_bulk_sms_to_parents(students, message, created_by=request.user)
                queued = result['queued']
                errors = result['errors']
                
            elif recipient_type == 'class_students' and course_id:
                course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
                course = course_qs.get(id=course_id)
                result = send_bulk_sms_to_class(course, message, include_parents=False, created_by=request.user)
                queued = result['queued']
                errors = result['errors']
                
            elif recipient_type == 'class_parents' and course_id:
                course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
                course = course_qs.get(id=course_id)
                result = send_bulk_sms_to_class(course, message, include_parents=True, created_by=request.user)
                queued = result['queued']
                errors = result['errors']
                
            elif recipient_type == 'grade_students' and grade_level_id:
                students = Student.objects.filter(course__grade_level_id=grade_level_id)
                if school:
                    students = students.filter(admin__school=school)
                result = send_bulk_sms_to_students(students, message, created_by=request.user)
                queued = result['queued']
                errors = result['errors']
                
            elif recipient_type == 'grade_parents' and grade_level_id:
                students = Student.objects.filter(course__grade_level_id=grade_level_id)
                if school:
                    students = students.filter(admin__school=school)
                result = send_bulk_sms_to_parents(students, message, created_by=request.user)
                queued = result['queued']
                errors = result['errors']
                
            elif recipient_type == 'custom' and custom_numbers:
                numbers = [n.strip() for n in custom_numbers.split('\n') if n.strip()]
                for phone in numbers:
                    add_result = add_to_sms_queue(
                        phone_number=phone,
                        message=message,
                        recipient_type='custom',
                        batch_id=batch_id,
                        created_by=request.user
                    )
                    if add_result['success']:
                        queued += 1
                    else:
                        errors.append(f"{phone}: {add_result['error']}")
            
            if queued > 0:
                messages.success(request, f"Successfully queued {queued} SMS messages for delivery")
            if errors:
                messages.warning(request, f"Errors: {', '.join(errors[:5])}" + (f" and {len(errors)-5} more" if len(errors) > 5 else ""))
                
        except Exception as e:
            messages.error(request, f"Error sending SMS: {str(e)}")
        
        return redirect('bulk_sms')
    
    context = {
        'courses': Course.objects.filter(school=school, is_active=True).select_related('grade_level') if school else Course.objects.filter(is_active=True).select_related('grade_level'),
        'grade_levels': GradeLevel.objects.filter(school=school, is_active=True) if school else GradeLevel.objects.filter(is_active=True),
        'templates': SMSTemplate.objects.filter(created_by__school=school, is_active=True) if school else SMSTemplate.objects.filter(is_active=True),
        'page_title': 'Send Bulk SMS'
    }
    return render(request, 'hod_template/bulk_sms.html', context)


def sms_templates(request):
    """Manage SMS templates"""
    if request.method == 'POST':
        form = SMSTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.save()
            messages.success(request, "Template created successfully")
            return redirect('sms_templates')
    else:
        form = SMSTemplateForm()
    
    school = getattr(request, 'school', None)
    templates = SMSTemplate.objects.filter(created_by__school=school) if school else SMSTemplate.objects.all()
    context = {
        'form': form,
        'templates': templates,
        'page_title': 'SMS Templates'
    }
    return render(request, 'hod_template/sms_templates.html', context)


def edit_sms_template(request, template_id):
    """Edit SMS template"""
    school = getattr(request, 'school', None)
    template_qs = SMSTemplate.objects.filter(created_by__school=school) if school else SMSTemplate.objects.all()
    template = get_object_or_404(template_qs, id=template_id)
    
    if request.method == 'POST':
        form = SMSTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Template updated successfully")
            return redirect('sms_templates')
    else:
        form = SMSTemplateForm(instance=template)
    
    context = {
        'form': form,
        'template': template,
        'page_title': 'Edit SMS Template'
    }
    return render(request, 'hod_template/edit_sms_template.html', context)


def delete_sms_template(request, template_id):
    """Delete SMS template"""
    school = getattr(request, 'school', None)
    template_qs = SMSTemplate.objects.filter(created_by__school=school) if school else SMSTemplate.objects.all()
    template = get_object_or_404(template_qs, id=template_id)
    template.delete()
    messages.success(request, "Template deleted")
    return redirect('sms_templates')


def sms_reports(request):
    """View SMS delivery reports - school-scoped so each school only sees its own SMS data"""
    school = getattr(request, 'school', None)
    queue_stats = get_sms_queue_stats(school=school)
    # Filter logs by school: via queue_item->created_by->school (excludes legacy logs with null queue_item)
    recent_logs = SMSLog.objects.filter(queue_item__created_by__school=school)[:100] if school else SMSLog.objects.all()[:100]
    pending_sms = SMSQueue.objects.filter(status='pending')
    if school:
        pending_sms = pending_sms.filter(created_by__school=school)
    pending_sms = pending_sms.count()
    
    context = {
        'queue_stats': queue_stats,
        'recent_logs': recent_logs,
        'pending_sms': pending_sms,
        'page_title': 'SMS Reports'
    }
    return render(request, 'hod_template/sms_reports.html', context)


def process_sms_queue_view(request):
    """Manually trigger SMS queue processing - processes only current school's queue"""
    school = getattr(request, 'school', None)
    result = process_sms_queue(batch_size=50, school=school)
    messages.success(request, f"Processed {result['processed']} SMS: {result['success']} sent, {result['failed']} failed")
    return redirect('sms_reports')


# ============================================
# FEE MANAGEMENT VIEWS
# ============================================

def manage_fee_types(request):
    """Manage fee types (school-scoped - each school has its own)"""
    school = getattr(request, 'school', None)
    if request.method == 'POST':
        form = FeeTypeForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if school:
                obj.school = school
            obj.save()
            messages.success(request, "Fee type created successfully")
            return redirect('manage_fee_types')
    else:
        form = FeeTypeForm()
    
    fee_types = FeeType.objects.filter(school=school) if school else FeeType.objects.all()
    context = {
        'form': form,
        'fee_types': fee_types,
        'page_title': 'Manage Fee Types'
    }
    return render(request, 'hod_template/manage_fee_types.html', context)


def edit_fee_type(request, fee_type_id):
    """Edit fee type"""
    school = getattr(request, 'school', None)
    qs = FeeType.objects.filter(school=school) if school else FeeType.objects.all()
    fee_type = get_object_or_404(qs, id=fee_type_id)
    
    if request.method == 'POST':
        form = FeeTypeForm(request.POST, instance=fee_type)
        if form.is_valid():
            form.save()
            messages.success(request, "Fee type updated")
            return redirect('manage_fee_types')
    else:
        form = FeeTypeForm(instance=fee_type)
    
    context = {
        'form': form,
        'fee_type': fee_type,
        'page_title': 'Edit Fee Type'
    }
    return render(request, 'hod_template/edit_fee_type.html', context)


def delete_fee_type(request, fee_type_id):
    """Delete fee type (school-scoped)."""
    school = getattr(request, 'school', None)
    qs = FeeType.objects.filter(school=school) if school else FeeType.objects.all()
    fee_type = get_object_or_404(qs, id=fee_type_id)
    try:
        fee_type.delete()
        messages.success(request, "Fee type deleted successfully.")
    except Exception as e:
        messages.error(request, f"Cannot delete: {str(e)}")
    return redirect('manage_fee_types')


def manage_fee_groups(request):
    """Manage fee groups (school-scoped - each school has its own)"""
    school = getattr(request, 'school', None)
    if request.method == 'POST':
        form = FeeGroupForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if school:
                obj.school = school
            obj.save()
            messages.success(request, "Fee group created successfully")
            return redirect('manage_fee_groups')
    else:
        form = FeeGroupForm()
    
    fee_groups = FeeGroup.objects.filter(school=school).prefetch_related('fee_items__fee_type') if school else FeeGroup.objects.prefetch_related('fee_items__fee_type').all()
    context = {
        'form': form,
        'fee_groups': fee_groups,
        'page_title': 'Manage Fee Groups'
    }
    return render(request, 'hod_template/manage_fee_groups.html', context)


def edit_fee_group(request, group_id):
    """Edit fee group and its items"""
    school = getattr(request, 'school', None)
    qs = FeeGroup.objects.filter(school=school) if school else FeeGroup.objects.all()
    fee_group = get_object_or_404(qs, id=group_id)
    
    if request.method == 'POST':
        form = FeeGroupForm(request.POST, instance=fee_group)
        if form.is_valid():
            form.save()
            
            # Update fee items (use school's fee types only)
            fee_types = FeeType.objects.filter(school=school, is_active=True) if school else FeeType.objects.filter(is_active=True)
            for fee_type in fee_types:
                amount_key = f'amount_{fee_type.id}'
                if amount_key in request.POST and request.POST[amount_key]:
                    amount = Decimal(request.POST[amount_key])
                    FeeGroupItem.objects.update_or_create(
                        fee_group=fee_group,
                        fee_type=fee_type,
                        defaults={'amount': amount}
                    )
            
            messages.success(request, "Fee group updated")
            return redirect('manage_fee_groups')
    else:
        form = FeeGroupForm(instance=fee_group)
    
    fee_types = FeeType.objects.filter(school=school, is_active=True) if school else FeeType.objects.filter(is_active=True)
    existing_items = {item.fee_type_id: item.amount for item in fee_group.fee_items.all()}
    fee_type_amounts = [(ft, existing_items.get(ft.id, '')) for ft in fee_types]
    
    context = {
        'form': form,
        'fee_group': fee_group,
        'fee_type_amounts': fee_type_amounts,
        'page_title': 'Edit Fee Group'
    }
    return render(request, 'hod_template/edit_fee_group.html', context)


def delete_fee_group(request, group_id):
    """Delete fee group (school-scoped)."""
    school = getattr(request, 'school', None)
    qs = FeeGroup.objects.filter(school=school) if school else FeeGroup.objects.all()
    fee_group = get_object_or_404(qs, id=group_id)
    try:
        fee_group.delete()
        messages.success(request, "Fee group deleted successfully.")
    except Exception as e:
        messages.error(request, f"Cannot delete: {str(e)}")
    return redirect('manage_fee_groups')


def _check_finance_permission(request, require_manage=False):
    """Check if user can view (or manage) finance. Returns (allowed, redirect_response)."""
    # Finance Officer (user_type='5') has full finance access
    if str(request.user.user_type) == '5':
        return True, None
    if request.user.is_superuser:
        return True, None
    # School Admin (user_type='1') has full access to control all school activities
    if str(request.user.user_type) == '1':
        return True, None
    try:
        perm = AdminPermission.objects.get(admin=request.user)
        if require_manage:
            if not perm.can_manage_fees:
                return False, redirect('admin_home')
        else:
            if not perm.can_view_fees:
                return False, redirect('admin_home')
        return True, None
    except AdminPermission.DoesNotExist:
        return False, redirect('admin_home')


def finance_dashboard(request):
    """Finance Dashboard - summary cards, revenue by class, defaulters, recent transactions (school-scoped)"""
    allowed, resp = _check_finance_permission(request)
    if not allowed:
        messages.error(request, "You don't have permission to view the finance dashboard")
        return resp

    school = getattr(request, 'school', None)
    sessions = Session.objects.filter(school=school).order_by('-start_year') if school else Session.objects.order_by('-start_year').all()
    session_id = request.GET.get('session_id')
    if session_id:
        session = sessions.filter(id=session_id).first()
    else:
        # Default to active term's session when available
        active_term = AcademicTerm.get_active_term(school=school)
        if active_term:
            session = sessions.filter(academic_year=active_term.academic_year).first() or sessions.first()
        else:
            session = sessions.first()

    # If no session in DB, use empty aggregates
    if not session:
        student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.none()
        expense_qs = Expense.objects.filter(school=school) if school else Expense.objects.none()
        context = {
            'session': None,
            'sessions': sessions,
            'total_expected': 0,
            'total_collected': 0,
            'total_outstanding': 0,
            'students_with_arrears': 0,
            'total_students': student_qs.count(),
            'today_collection': Decimal('0'),
            'total_expenses': expense_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0'),
            'net_balance': Decimal('0'),
            'revenue_by_class': [],
            'defaulters': [],
            'recent_transactions': [],
            'monthly_revenue_labels': json.dumps([]),
            'monthly_revenue_data': json.dumps([]),
            'income_vs_expenses': json.dumps({'income': 0, 'expenses': 0, 'profit': 0}),
            'page_title': 'Finance Dashboard',
        }
        return render(request, 'hod_template/finance_dashboard.html', context)

    # Summary KPIs (filter by school)
    fee_balances = FeeBalance.objects.filter(session=session)
    if school:
        fee_balances = fee_balances.filter(student__admin__school=school)
    total_expected = fee_balances.aggregate(t=Sum('total_fees'))['t'] or Decimal('0')
    total_collected = fee_balances.aggregate(t=Sum('total_paid'))['t'] or Decimal('0')
    total_outstanding = fee_balances.aggregate(t=Sum('balance'))['t'] or Decimal('0')
    students_with_arrears = fee_balances.filter(balance__gt=0).count()

    # Revenue by class (Course) - school-scoped
    courses_qs = Course.objects.filter(school=school, is_active=True) if school else Course.objects.filter(is_active=True)
    revenue_by_class = []
    for course in courses_qs.order_by('name'):
        balances = fee_balances.filter(student__course=course)
        exp = balances.aggregate(t=Sum('total_fees'))['t'] or Decimal('0')
        paid = balances.aggregate(t=Sum('total_paid'))['t'] or Decimal('0')
        bal = balances.aggregate(t=Sum('balance'))['t'] or Decimal('0')
        if exp > 0 or paid > 0 or bal > 0:
            revenue_by_class.append({
                'class': course,
                'expected': exp,
                'paid': paid,
                'balance': bal,
            })

    # Defaulters (students with balance > 0)
    defaulters = fee_balances.filter(balance__gt=0).select_related(
        'student__admin', 'student__course'
    ).order_by('-balance')[:50]

    # Recent transactions - school-scoped
    recent_transactions = FeePayment.objects.filter(
        session=session, is_reversed=False
    ).select_related('student__admin', 'received_by')
    if school:
        recent_transactions = recent_transactions.filter(student__admin__school=school)
    recent_transactions = recent_transactions.order_by('-payment_date')[:20]

    # Additional stats: total students, today's collection, expenses, net balance
    student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    total_students = student_qs.count()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_payments = FeePayment.objects.filter(
        session=session, is_reversed=False, payment_date__gte=today_start
    )
    if school:
        today_payments = today_payments.filter(student__admin__school=school)
    today_collection = today_payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    expense_qs = Expense.objects.filter(school=school) if school else Expense.objects.filter(school__isnull=True)
    total_expenses = expense_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    net_balance = total_collected - total_expenses

    # Monthly revenue (last 6 months) for chart
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_payments = FeePayment.objects.filter(
        session=session, is_reversed=False, payment_date__gte=six_months_ago
    )
    if school:
        monthly_payments = monthly_payments.filter(student__admin__school=school)
    monthly_agg = monthly_payments.annotate(
        month=TruncMonth('payment_date')
    ).values('month').annotate(total=Sum('amount')).order_by('month')
    monthly_revenue_labels = []
    monthly_revenue_data = []
    for row in monthly_agg:
        monthly_revenue_labels.append(row['month'].strftime('%b %Y'))
        monthly_revenue_data.append(float(row['total'] or 0))

    # Income vs Expenses for chart
    income_vs_expenses = {
        'income': float(total_collected),
        'expenses': float(total_expenses),
        'profit': float(net_balance),
    }

    context = {
        'session': session,
        'sessions': sessions,
        'total_expected': total_expected,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'students_with_arrears': students_with_arrears,
        'total_students': total_students,
        'today_collection': today_collection,
        'total_expenses': total_expenses,
        'net_balance': net_balance,
        'revenue_by_class': revenue_by_class,
        'defaulters': defaulters,
        'recent_transactions': recent_transactions,
        'monthly_revenue_labels': json.dumps(monthly_revenue_labels),
        'monthly_revenue_data': json.dumps(monthly_revenue_data),
        'income_vs_expenses': json.dumps(income_vs_expenses),
        'page_title': 'Finance Dashboard',
    }
    return render(request, 'hod_template/finance_dashboard.html', context)


def manage_fee_structures(request):
    """Manage fee structures - school-scoped, new schools see empty list"""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        messages.error(request, "You don't have permission to manage fee structures")
        return resp

    school = getattr(request, 'school', None)
    if request.method == 'POST':
        form = FeeStructureForm(request.POST, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Fee structure created successfully.")
                return redirect('manage_fee_structures')
            except Exception as e:
                messages.error(request, f"Could not save: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = FeeStructureForm(school=school)

    structures = FeeStructure.objects.select_related(
        'fee_group', 'grade_level', 'course', 'session'
    )
    if school:
        structures = structures.filter(session__school=school)
    
    context = {
        'form': form,
        'structures': structures,
        'page_title': 'Manage Fee Structures'
    }
    return render(request, 'hod_template/manage_fee_structures.html', context)


def delete_fee_structure(request, structure_id):
    """Delete fee structure (school-scoped via session)."""
    school = getattr(request, 'school', None)
    qs = FeeStructure.objects.select_related('session')
    if school:
        qs = qs.filter(session__school=school)
    structure = get_object_or_404(qs, id=structure_id)
    try:
        structure.delete()
        messages.success(request, "Fee structure deleted successfully.")
    except Exception as e:
        messages.error(request, f"Cannot delete: {str(e)}")
    return redirect('manage_fee_structures')


def manage_expenses(request):
    """Manage school expenses - school-scoped."""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        messages.error(request, "You don't have permission to manage expenses")
        return resp

    school = getattr(request, 'school', None)
    expenses = Expense.objects.filter(school=school).select_related('recorded_by').order_by('-expense_date', '-created_at')
    total_expenses = expenses.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    context = {
        'expenses': expenses,
        'total_expenses': total_expenses,
        'page_title': 'Manage Expenses',
    }
    return render(request, 'hod_template/manage_expenses.html', context)


def add_expense(request):
    """Add new expense - school-scoped."""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        messages.error(request, "You don't have permission to add expenses")
        return resp

    school = getattr(request, 'school', None)
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.school = school
            obj.recorded_by = request.user
            obj.save()
            messages.success(request, "Expense recorded successfully.")
            return redirect('manage_expenses')
    else:
        form = ExpenseForm()
    context = {'form': form, 'page_title': 'Add Expense'}
    return render(request, 'hod_template/add_expense.html', context)


def edit_expense(request, expense_id):
    """Edit expense - school-scoped."""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        messages.error(request, "You don't have permission to edit expenses")
        return resp

    school = getattr(request, 'school', None)
    qs = Expense.objects.filter(school=school)
    expense = get_object_or_404(qs, id=expense_id)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated successfully.")
            return redirect('manage_expenses')
    else:
        form = ExpenseForm(instance=expense)
    context = {'form': form, 'expense': expense, 'page_title': 'Edit Expense'}
    return render(request, 'hod_template/edit_expense.html', context)


def delete_expense(request, expense_id):
    """Delete expense - school-scoped."""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        messages.error(request, "You don't have permission to delete expenses")
        return resp

    school = getattr(request, 'school', None)
    qs = Expense.objects.filter(school=school)
    expense = get_object_or_404(qs, id=expense_id)
    expense.delete()
    messages.success(request, "Expense deleted successfully.")
    return redirect('manage_expenses')


def fee_collection(request):
    """Fee collection / payment recording"""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        messages.error(request, "You don't have permission to record payments")
        return resp

    if request.method == 'POST':
        student_id = request.POST.get('student')
        amount = Decimal(request.POST.get('amount', 0))
        payment_mode = request.POST.get('payment_mode')
        paid_by = request.POST.get('paid_by', '').strip() or None
        transaction_ref = request.POST.get('transaction_ref', '')
        description = request.POST.get('notes', '')  # Form field is 'notes', model field is 'description'

        school = getattr(request, 'school', None)
        try:
            student_qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
            student = student_qs.get(id=student_id)
            # Use active term's session, or latest session (school-scoped)
            session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
            active_term = AcademicTerm.get_active_term(school=school)
            if active_term:
                session = session_qs.filter(academic_year=active_term.academic_year).first() or session_qs.order_by('-start_year').first()
            else:
                session = session_qs.order_by('-start_year').first()

            # Generate receipt number
            school_settings = get_school_settings(school=getattr(request, 'school', None))
            receipt_number = school_settings.get_next_receipt_number()

            # Create payment record
            payment = FeePayment.objects.create(
                student=student,
                session=session,
                amount=amount,
                payment_mode=payment_mode,
                receipt_number=receipt_number,
                transaction_ref=transaction_ref,
                payment_date=timezone.now(),
                received_by=request.user,
                paid_by=paid_by,
                description=description
            )
            
            # Update fee balance
            fee_balance, created = FeeBalance.objects.get_or_create(
                student=student,
                session=session,
                defaults={'total_fees': 0}
            )
            fee_balance.update_balance()
            
            # Send receipt SMS
            send_payment_receipt_sms(payment, created_by=request.user)
            
            # Notify parent(s) of the student
            for parent in Parent.objects.filter(children=student).select_related('admin'):
                create_notification(
                    parent.admin,
                    "Fee Payment Received",
                    f"Payment of KES {amount:,.2f} recorded for {student.admin.first_name} {student.admin.last_name}. Receipt: {receipt_number}",
                    reverse('parent_view_child_fees', args=[student.id]),
                    school=school,
                )
            
            messages.success(request, f"Payment recorded. Receipt: {receipt_number}")
            return redirect('fee_collection')
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    school = getattr(request, 'school', None)
    students = Student.objects.filter(admin__school=school).select_related('admin', 'course') if school else Student.objects.select_related('admin', 'course').all()
    recent_payments = FeePayment.objects.filter(student__admin__school=school).select_related('student__admin').order_by('-created_at')[:20] if school else FeePayment.objects.select_related('student__admin').order_by('-created_at')[:20]
    
    context = {
        'students': students,
        'recent_payments': recent_payments,
        'payment_modes': FeePayment.PAYMENT_MODE_CHOICES,
        'page_title': 'Fee Collection'
    }
    return render(request, 'hod_template/fee_collection.html', context)


def student_fee_statement(request, student_id):
    """View student fee statement"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session = session_qs.order_by('-start_year').first()
    
    payments = FeePayment.objects.filter(
        student=student,
        is_reversed=False
    ).order_by('-payment_date')
    
    fee_balance = FeeBalance.objects.filter(
        student=student,
        session=session
    ).first()
    
    context = {
        'student': student,
        'payments': payments,
        'fee_balance': fee_balance,
        'page_title': f'Fee Statement - {student}'
    }
    return render(request, 'hod_template/student_fee_statement.html', context)


def print_fee_receipt(request, payment_id):
    """Generate and print fee receipt PDF - includes school logo, balance, finance officer"""
    school = getattr(request, 'school', None)
    payment_qs = FeePayment.objects.filter(student__admin__school=school) if school else FeePayment.objects.all()
    payment = get_object_or_404(payment_qs, id=payment_id)
    
    if not REPORTLAB_AVAILABLE:
        messages.error(request, 'PDF generation not available. Install reportlab.')
        return redirect('fee_collection')
    
    response = HttpResponse(content_type='application/pdf')
    filename = f"Receipt_{payment.receipt_number}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # School settings (use student's school for multi-tenant)
    student_school = getattr(payment.student.admin, 'school', None)
    settings_obj = get_school_settings(school=student_school or school)
    
    # School Logo (if available)
    if settings_obj.school_logo:
        try:
            logo_path = settings_obj.school_logo.path
            if os.path.exists(logo_path):
                img = Image(logo_path, width=1.2*inch, height=1.2*inch)
                elements.append(img)
                elements.append(Spacer(1, 10))
        except Exception:
            pass
    
    # School Header
    title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER)
    elements.append(Paragraph(settings_obj.school_name, title_style))
    elements.append(Paragraph("FEE PAYMENT RECEIPT", styles['Heading2']))
    elements.append(Spacer(1, 20))
    
    # Get fee balance for receipt
    fee_balance = FeeBalance.objects.filter(
        student=payment.student,
        session=payment.session
    ).first()
    balance_after = fee_balance.balance if fee_balance else Decimal('0')
    
    # Receipt Details
    data = [
        ['Receipt Number:', payment.receipt_number],
        ['Date:', payment.payment_date.strftime('%d/%m/%Y %H:%M')],
        ['Student Name:', f"{payment.student.admin.first_name} {payment.student.admin.last_name}"],
        ['Admission Number:', payment.student.admission_number or 'N/A'],
        ['Class:', str(payment.student.course) if payment.student.course else 'N/A'],
        ['Amount Paid:', f"KES {payment.amount:,.2f}"],
        ['Balance:', f"KES {balance_after:,.2f}"],
        ['Payment Method:', payment.get_payment_mode_display()],
        ['Transaction Ref:', payment.transaction_ref or 'N/A'],
        ['Received By:', payment.received_by.get_full_name() if payment.received_by else 'N/A'],
    ]
    
    table = Table(data, colWidths=[2*inch, 4*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(table)
    
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("_" * 30, styles['Normal']))
    elements.append(Paragraph("Authorized Signature", styles['Normal']))
    
    doc.build(elements)
    return response


def print_fee_statement(request, student_id):
    """Generate student fee statement PDF"""
    student = get_object_or_404(Student, id=student_id)
    
    if not REPORTLAB_AVAILABLE:
        messages.error(request, 'PDF generation not available. Install reportlab.')
        return redirect('student_fee_statement', student_id=student_id)
    
    payments = FeePayment.objects.filter(
        student=student,
        is_reversed=False
    ).order_by('payment_date')
    
    session = Session.objects.order_by('-start_year').first()
    fee_balance = FeeBalance.objects.filter(student=student, session=session).first()
    
    response = HttpResponse(content_type='application/pdf')
    filename = f"FeeStatement_{student.admission_number or student.id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Header
    school = get_school_settings(school=getattr(request, 'school', None))
    title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER)
    elements.append(Paragraph(school.school_name, title_style))
    elements.append(Paragraph("STUDENT FEE STATEMENT", styles['Heading2']))
    elements.append(Spacer(1, 20))
    
    # Student Info
    elements.append(Paragraph(f"Student: {student}", styles['Normal']))
    elements.append(Paragraph(f"Admission No: {student.admission_number or 'N/A'}", styles['Normal']))
    elements.append(Paragraph(f"Class: {student.course or 'N/A'}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Payment History Table
    data = [['Date', 'Receipt No.', 'Mode', 'Amount']]
    total_paid = Decimal('0')
    for payment in payments:
        data.append([
            payment.payment_date.strftime('%d/%m/%Y'),
            payment.receipt_number,
            payment.get_payment_mode_display(),
            f"KES {payment.amount:,.2f}"
        ])
        total_paid += payment.amount
    
    data.append(['', '', 'Total Paid:', f"KES {total_paid:,.2f}"])
    
    if fee_balance:
        data.append(['', '', 'Total Fees:', f"KES {fee_balance.total_fees:,.2f}"])
        data.append(['', '', 'Balance:', f"KES {fee_balance.balance:,.2f}"])
    
    table = Table(data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    
    doc.build(elements)
    return response


def finance_term_report(request):
    """Term Revenue Report - print-friendly (school-scoped)"""
    allowed, resp = _check_finance_permission(request)
    if not allowed:
        return resp

    school = getattr(request, 'school', None)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session_id = request.GET.get('session_id')
    session = session_qs.filter(id=session_id).first() if session_id else session_qs.order_by('-start_year').first()
    if not session:
        messages.error(request, "No session selected")
        return redirect('finance_dashboard')

    fee_balances = FeeBalance.objects.filter(session=session)
    if school:
        fee_balances = fee_balances.filter(student__admin__school=school)
    total_expected = fee_balances.aggregate(t=Sum('total_fees'))['t'] or Decimal('0')
    total_collected = fee_balances.aggregate(t=Sum('total_paid'))['t'] or Decimal('0')
    total_outstanding = fee_balances.aggregate(t=Sum('balance'))['t'] or Decimal('0')

    context = {
        'session': session,
        'total_expected': total_expected,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'page_title': f'Term Revenue Report - {session}',
    }
    return render(request, 'hod_template/finance_term_report.html', context)


def _create_fee_balance_for_enrollment(student, school_class, session, active_term=None):
    """
    Auto-bill student when enrolled: create FeeBalance from FeeStructure for class+session.
    Called from add_enrollment and bulk_enrollment.
    """
    structure = FeeStructure.objects.filter(
        course=school_class,
        session=session,
        is_active=True
    ).select_related('fee_group').first()

    total_fees = Decimal('0')
    due_date = None
    fee_structure = None

    if structure:
        fee_structure = structure
        total_fees = sum(item.amount for item in structure.fee_group.fee_items.all())
        due_date = structure.due_date

    fb, created = FeeBalance.objects.get_or_create(
        student=student,
        session=session,
        defaults={
            'total_fees': total_fees,
            'fee_structure': fee_structure,
            'due_date': due_date,
        }
    )
    # Update when: new structure has fees and (old was zero OR class/structure changed e.g. transfer)
    if not created and total_fees > 0:
        new_struct_id = fee_structure.id if fee_structure else None
        if fb.total_fees == 0 or (new_struct_id and fb.fee_structure_id != new_struct_id):
            fb.total_fees = total_fees
            fb.fee_structure = fee_structure
            fb.due_date = due_date
            fb.update_balance()
    return fb


def finance_generate_invoices(request):
    """Generate FeeBalance records for enrolled students from FeeStructure (school-scoped)"""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        return resp

    school = getattr(request, 'school', None)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session_id = request.GET.get('session_id')
    session = session_qs.filter(id=session_id).first() if session_id else session_qs.order_by('-start_year').first()
    if not session:
        messages.error(request, "No session selected")
        return redirect('finance_dashboard')

    created = 0
    updated = 0
    students_qs = Student.objects.filter(course__isnull=False).select_related('course')
    if school:
        students_qs = students_qs.filter(admin__school=school)
    for student in students_qs:
        # Get fee structure for this class + session
        structure = FeeStructure.objects.filter(
            course=student.course,
            session=session,
            is_active=True
        ).select_related('fee_group').first()

        total_fees = Decimal('0')
        if structure and structure.fee_group:
            total_fees = sum(
                item.amount for item in structure.fee_group.fee_items.all()
            )

        fb, created_fb = FeeBalance.objects.get_or_create(
            student=student,
            session=session,
            defaults={'total_fees': total_fees}
        )
        if created_fb:
            created += 1
        elif fb.total_fees != total_fees and total_fees > 0:
            fb.total_fees = total_fees
            if structure:
                fb.fee_structure = structure
                fb.due_date = structure.due_date
            fb.update_balance()
            updated += 1

    messages.success(request, f"Invoices generated: {created} created, {updated} updated")
    url = reverse('finance_dashboard')
    if session:
        url += f'?session_id={session.id}'
    return redirect(url)


def finance_class_report(request):
    """Class Collection Report - print-friendly (school-scoped)"""
    allowed, resp = _check_finance_permission(request)
    if not allowed:
        return resp

    school = getattr(request, 'school', None)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session_id = request.GET.get('session_id')
    session = session_qs.filter(id=session_id).first() if session_id else session_qs.order_by('-start_year').first()
    if not session:
        messages.error(request, "No session selected")
        return redirect('finance_dashboard')

    fee_balances = FeeBalance.objects.filter(session=session)
    if school:
        fee_balances = fee_balances.filter(student__admin__school=school)
    revenue_by_class = []
    courses_qs = Course.objects.filter(school=school, is_active=True) if school else Course.objects.filter(is_active=True)
    for course in courses_qs.order_by('name'):
        balances = fee_balances.filter(student__course=course)
        exp = balances.aggregate(t=Sum('total_fees'))['t'] or Decimal('0')
        paid = balances.aggregate(t=Sum('total_paid'))['t'] or Decimal('0')
        bal = balances.aggregate(t=Sum('balance'))['t'] or Decimal('0')
        revenue_by_class.append({'class': course, 'expected': exp, 'paid': paid, 'balance': bal})

    context = {
        'session': session,
        'revenue_by_class': revenue_by_class,
        'page_title': f'Class Collection Report - {session}',
    }
    return render(request, 'hod_template/finance_class_report.html', context)


def finance_daily_report(request):
    """Daily Collection Report - payments by date (school-scoped)"""
    allowed, resp = _check_finance_permission(request)
    if not allowed:
        return resp

    school = getattr(request, 'school', None)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session_id = request.GET.get('session_id')
    session = session_qs.filter(id=session_id).first() if session_id else session_qs.order_by('-start_year').first()
    date_str = request.GET.get('date')
    if date_str:
        try:
            from datetime import datetime
            report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            report_date = timezone.now().date()
    else:
        report_date = timezone.now().date()

    if session:
        payments = FeePayment.objects.filter(
            session=session, is_reversed=False
        ).filter(
            payment_date__date=report_date
        ).select_related('student__admin')
        if school:
            payments = payments.filter(student__admin__school=school)
        payments = payments.order_by('-payment_date')
    else:
        payments = FeePayment.objects.none()
    total_today = payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    context = {
        'session': session,
        'sessions': session_qs.order_by('-start_year'),
        'report_date': report_date,
        'payments': payments,
        'total_today': total_today,
        'page_title': f'Daily Collection Report - {report_date}',
    }
    return render(request, 'hod_template/finance_daily_report.html', context)


def finance_expense_report(request):
    """Expense Report - all expenses (school-scoped)"""
    allowed, resp = _check_finance_permission(request)
    if not allowed:
        return resp

    school = getattr(request, 'school', None)
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    expenses = Expense.objects.filter(school=school).select_related('recorded_by').order_by('-expense_date')
    if date_from:
        try:
            from datetime import datetime
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            expenses = expenses.filter(expense_date__gte=df)
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            expenses = expenses.filter(expense_date__lte=dt)
        except ValueError:
            pass
    total_expenses = expenses.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # By category with display names
    from django.db.models import Count
    cat_choices = dict(Expense.CATEGORY_CHOICES)
    by_category = []
    for row in expenses.values('category').annotate(
        total=Sum('amount'), count=Count('id')
    ).order_by('-total'):
        row['category_display'] = cat_choices.get(row['category'], row['category'])
        by_category.append(row)

    context = {
        'expenses': expenses,
        'total_expenses': total_expenses,
        'by_category': by_category,
        'page_title': 'Expense Report',
    }
    return render(request, 'hod_template/finance_expense_report.html', context)


def send_fee_reminders(request):
    """Send fee reminders to students with outstanding balances (school-scoped)"""
    allowed, resp = _check_finance_permission(request, require_manage=True)
    if not allowed:
        return resp

    school = getattr(request, 'school', None)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session_id = request.GET.get('session_id')
    session = session_qs.filter(id=session_id).first() if session_id else session_qs.order_by('-start_year').first()
    if not session:
        messages.info(request, "No session found. Create a session first.")
        return redirect('finance_dashboard')
    balances = FeeBalance.objects.filter(
        session=session,
        balance__gt=0
    ).select_related('student__admin')
    if school:
        balances = balances.filter(student__admin__school=school)
    
    sent_count = 0
    for balance in balances:
        structure = balance.fee_structure
        due_date = structure.due_date if structure else None
        send_fee_reminder_sms(balance.student, balance.balance, due_date, created_by=request.user)
        sent_count += 1
    
    # Process the queue
    process_sms_queue()
    
    messages.success(request, f"Fee reminders sent to {sent_count} students/parents")
    url = reverse('finance_dashboard')
    if session:
        url += f'?session_id={session.id}'
    return redirect(url)


# ============================================
# EXAM MANAGEMENT VIEWS
# ============================================

def manage_exam_types(request):
    """Manage exam types (school-scoped)"""
    from django.db import IntegrityError
    school = getattr(request, 'school', None)
    if request.method == 'POST':
        form = ExamTypeForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if school:
                obj.school = school
            try:
                obj.save()
                messages.success(request, "Exam type created")
                return redirect('manage_exam_types')
            except IntegrityError:
                messages.error(request, "An exam type with this code already exists for your school. Please use a different code.")
    else:
        form = ExamTypeForm()
    
    exam_types = ExamType.objects.filter(school=school) if school else ExamType.objects.all()
    context = {
        'form': form,
        'exam_types': exam_types,
        'page_title': 'Manage Exam Types'
    }
    return render(request, 'hod_template/manage_exam_types.html', context)


def edit_exam_type(request, exam_type_id):
    """Edit exam type (school-scoped)."""
    from django.db import IntegrityError
    school = getattr(request, 'school', None)
    qs = ExamType.objects.filter(school=school) if school else ExamType.objects.all()
    exam_type = get_object_or_404(qs, id=exam_type_id)
    if request.method == 'POST':
        form = ExamTypeForm(request.POST, instance=exam_type)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Exam type updated.")
                return redirect('manage_exam_types')
            except IntegrityError:
                messages.error(request, "An exam type with this code already exists. Please use a different code.")
    else:
        form = ExamTypeForm(instance=exam_type)
    context = {
        'form': form,
        'exam_type': exam_type,
        'page_title': 'Edit Exam Type'
    }
    return render(request, 'hod_template/edit_exam_type.html', context)


def delete_exam_type(request, exam_type_id):
    """Delete exam type (school-scoped)."""
    from django.db import IntegrityError
    school = getattr(request, 'school', None)
    qs = ExamType.objects.filter(school=school) if school else ExamType.objects.all()
    exam_type = get_object_or_404(qs, id=exam_type_id)
    try:
        exam_type.delete()
        messages.success(request, "Exam type deleted successfully.")
    except Exception as e:
        messages.error(request, f"Cannot delete: {str(e)}")
    return redirect('manage_exam_types')


def manage_exam_schedules(request):
    """Manage exam schedules and result entry windows (school-scoped)"""
    school = getattr(request, 'school', None)
    schedule_qs = ExamSchedule.objects.filter(session__school=school) if school else ExamSchedule.objects.all()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'open_result_entry':
            schedule_id = request.POST.get('schedule_id')
            schedule = get_object_or_404(schedule_qs, id=schedule_id)
            schedule.result_entry_open = True
            schedule.result_entry_status = 'open'
            schedule.save()
            messages.success(request, f"Result upload opened for {schedule.name}")
            return redirect('manage_exam_schedules')
        elif action == 'close_result_entry':
            schedule_id = request.POST.get('schedule_id')
            schedule = get_object_or_404(schedule_qs, id=schedule_id)
            schedule.result_entry_open = False
            schedule.result_entry_status = 'closed'
            schedule.save()
            messages.success(request, f"Result upload closed for {schedule.name}")
            return redirect('manage_exam_schedules')
        elif action == 'set_deadline':
            schedule_id = request.POST.get('schedule_id')
            end_date = request.POST.get('result_entry_end_date')
            schedule = get_object_or_404(schedule_qs, id=schedule_id)
            if end_date:
                schedule.result_entry_end_date = end_date
                schedule.save()
                messages.success(request, f"Upload deadline set for {schedule.name}")
            return redirect('manage_exam_schedules')
        form = ExamScheduleForm(request.POST, school=school)
        if form.is_valid():
            form.save()
            messages.success(request, "Exam schedule created")
            return redirect('manage_exam_schedules')
    else:
        form = ExamScheduleForm(school=school)
    schedules_qs = ExamSchedule.objects.select_related('exam_type', 'session')
    result_windows_qs = ResultEntryWindow.objects.select_related('session', 'academic_term')
    if school:
        schedules_qs = schedules_qs.filter(session__school=school)
        result_windows_qs = result_windows_qs.filter(session__school=school)
    context = {
        'form': form,
        'schedules': schedules_qs.all(),
        'result_windows': result_windows_qs.all(),
        'page_title': 'Manage Exam Schedules'
    }
    return render(request, 'hod_template/manage_exam_schedules.html', context)


def manage_result_entry(request):
    """MVP: Admin controls when teachers can enter legacy results (Add Result, Edit Result). School-scoped."""
    school = getattr(request, 'school', None)
    window_qs = ResultEntryWindow.objects.filter(session__school=school) if school else ResultEntryWindow.objects.all()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_window':
            session_id = request.POST.get('session')
            name = request.POST.get('name', 'Result Entry')
            if school and not Session.objects.filter(school=school, id=session_id).exists():
                messages.error(request, "Invalid session for your school.")
                return redirect('manage_result_entry')
            window = ResultEntryWindow.objects.create(
                session_id=session_id,
                name=name,
                result_entry_open=False,
                status='draft'
            )
            messages.success(request, f"Result entry window '{window.name}' created.")
            return redirect('manage_result_entry')
        elif action == 'open_upload':
            window_id = request.POST.get('window_id')
            window = get_object_or_404(window_qs, id=window_id)
            window.result_entry_open = True
            window.status = 'open'
            window.save()
            messages.success(request, f"Result upload opened for {window.name}")
            return redirect('manage_result_entry')
        elif action == 'close_upload':
            window_id = request.POST.get('window_id')
            window = get_object_or_404(ResultEntryWindow, id=window_id)
            window.result_entry_open = False
            window.status = 'closed'
            window.save()
            messages.success(request, f"Result upload closed for {window.name}")
            return redirect('manage_result_entry')
        elif action == 'set_deadline':
            window_id = request.POST.get('window_id')
            end_date = request.POST.get('result_entry_end_date')
            window = get_object_or_404(ResultEntryWindow, id=window_id)
            if end_date:
                window.result_entry_end_date = end_date
                window.save()
                messages.success(request, f"Upload deadline set for {window.name}")
            return redirect('manage_result_entry')
    windows_qs = ResultEntryWindow.objects.select_related('session', 'academic_term')
    sessions_qs = Session.objects.all()
    if school:
        windows_qs = windows_qs.filter(session__school=school)
        sessions_qs = sessions_qs.filter(school=school)
    context = {
        'windows': windows_qs.all(),
        'sessions': sessions_qs,
        'page_title': 'Manage Result Entry'
    }
    return render(request, 'hod_template/manage_result_entry.html', context)


def seed_default_grading_scale(request):
    """Add default 5-grade scale (80-100 A, 70-79 B, 60-69 C, 50-59 D, <50 E) for school."""
    school = getattr(request, 'school', None)
    if not school:
        messages.warning(request, "School context required.")
        return redirect('manage_grading_scale')
    existing = GradingScale.objects.filter(school=school, is_active=True).count()
    if existing > 0:
        messages.info(request, "You already have grading scale entries. Add or edit manually.")
        return redirect('manage_grading_scale')
    defaults = [
        (80, 100, 'A', 12, 'Excellent'),
        (70, 79, 'B', 10, 'Very Good'),
        (60, 69, 'C', 8, 'Good'),
        (50, 59, 'D', 6, 'Fair'),
        (0, 49, 'E', 4, 'Needs Improvement'),
    ]
    for min_m, max_m, grade, points, remarks in defaults:
        GradingScale.objects.create(
            school=school, name='Standard MVP',
            min_marks=min_m, max_marks=max_m,
            grade=grade, points=points, remarks=remarks, is_active=True
        )
    messages.success(request, "Default grading scale added (A 80-100, B 70-79, C 60-69, D 50-59, E 0-49).")
    return redirect('manage_grading_scale')


def manage_grading_scale(request):
    """Manage grading scale (school-scoped)"""
    school = getattr(request, 'school', None)
    if request.method == 'POST':
        form = GradingScaleForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if school:
                obj.school = school
            obj.save()
            messages.success(request, "Grading scale entry added")
            return redirect('manage_grading_scale')
    else:
        form = GradingScaleForm()
    
    grading_scales = GradingScale.objects.filter(school=school) if school else GradingScale.objects.all()
    has_scale = grading_scales.filter(is_active=True).exists()
    context = {
        'form': form,
        'grading_scales': grading_scales,
        'has_scale': has_scale,
        'page_title': 'Manage Grading Scale'
    }
    return render(request, 'hod_template/manage_grading_scale.html', context)


def edit_grading_scale(request, scale_id):
    """Edit grading scale entry (school-scoped)."""
    school = getattr(request, 'school', None)
    qs = GradingScale.objects.filter(school=school) if school else GradingScale.objects.all()
    scale = get_object_or_404(qs, id=scale_id)
    if request.method == 'POST':
        form = GradingScaleForm(request.POST, instance=scale)
        if form.is_valid():
            form.save()
            messages.success(request, "Grading scale entry updated.")
            return redirect('manage_grading_scale')
    else:
        form = GradingScaleForm(instance=scale)
    context = {
        'form': form,
        'scale': scale,
        'page_title': 'Edit Grading Scale'
    }
    return render(request, 'hod_template/edit_grading_scale.html', context)


def delete_grading_scale(request, scale_id):
    """Delete grading scale entry (school-scoped)."""
    school = getattr(request, 'school', None)
    qs = GradingScale.objects.filter(school=school) if school else GradingScale.objects.all()
    scale = get_object_or_404(qs, id=scale_id)
    try:
        scale.delete()
        messages.success(request, "Grading scale entry deleted successfully.")
    except Exception as e:
        messages.error(request, f"Cannot delete: {str(e)}")
    return redirect('manage_grading_scale')


def enter_exam_results(request):
    """Enter exam results. Term + Class + Subject: CAT (Opener), Mid Term, End Term in one form."""
    school = getattr(request, 'school', None)
    if not school:
        messages.warning(request, "School context required.")
        return redirect('admin_home')

    academic_terms = AcademicTerm.objects.filter(school=school).order_by('-academic_year', 'term_name')
    courses = Course.objects.filter(school=school, is_active=True).order_by('name')
    all_subjects_qs = Subject.objects.filter(course__school=school).select_related('course').order_by('course__name', 'name')
    if request.user.user_type == '2' and hasattr(request.user, 'staff'):
        all_subjects_qs = all_subjects_qs.filter(staff=request.user.staff)
    all_subjects = all_subjects_qs

    term_id = request.GET.get('term')
    class_id = request.GET.get('course') or request.GET.get('class')
    subject_id = request.GET.get('subject')

    if request.method == 'POST':
        active_term = AcademicTerm.get_active_term(school=school)
        if active_term and active_term.is_locked:
            messages.error(request, "Term is closed. Marks cannot be edited.")
            return redirect('enter_exam_results')
        term_id = request.POST.get('academic_term')
        class_id = request.POST.get('school_class')
        subject_id = request.POST.get('subject')
        academic_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
        school_class = get_object_or_404(Course, id=class_id, school=school)
        subject = get_object_or_404(Subject, id=subject_id, course=school_class)

        # Check if teacher has submitted (locked) - only admin can edit then
        staff = getattr(request.user, 'staff', None)
        if staff:
            try:
                sub = TeacherResultSubmission.objects.get(
                    staff=staff, subject=subject, academic_term=academic_term, school_class=school_class
                )
                if sub.status == 'submitted':
                    messages.error(request, "Results already submitted. Contact admin to unlock.")
                    return redirect(reverse('enter_exam_results') + f'?term={term_id}&course={class_id}&subject={subject_id}')
            except TeacherResultSubmission.DoesNotExist:
                pass

        for key, val in request.POST.items():
            if key.startswith('opener_') or key.startswith('midterm_') or key.startswith('endterm_'):
                parts = key.split('_')
                if len(parts) >= 2:
                    exam_type = parts[0]
                    sid = parts[1]
                    try:
                        student = Student.objects.get(id=sid, admin__school=school)
                    except (Student.DoesNotExist, ValueError):
                        continue
                    try:
                        v = min(100, max(0, float(val) if val else 0))
                    except ValueError:
                        v = 0
                    result, _ = KNECReportCardResult.objects.get_or_create(
                        student=student, subject=subject, academic_term=academic_term,
                        defaults={'opener_marks': 0, 'midterm_marks': 0, 'endterm_marks': 0}
                    )
                    if exam_type == 'opener':
                        result.opener_marks = v
                    elif exam_type == 'midterm':
                        result.midterm_marks = v
                    elif exam_type == 'endterm':
                        result.endterm_marks = v
                    result.save()
            elif key.startswith('comment_'):
                sid = key.replace('comment_', '')
                try:
                    student = Student.objects.get(id=sid, admin__school=school)
                    result = KNECReportCardResult.objects.filter(
                        student=student, subject=subject, academic_term=academic_term
                    ).first()
                    if result:
                        result.teacher_comment_override = request.POST.get(key, '').strip() or None
                        result.save()
                except (Student.DoesNotExist, ValueError):
                    pass

        # Ensure TeacherResultSubmission exists with status='draft' when marks are saved
        # Use subject's teacher (subject.staff) so submission status tracks the right person
        if subject:
            TeacherResultSubmission.objects.get_or_create(
                staff=subject.staff,
                subject=subject,
                academic_term=academic_term,
                school_class=school_class,
                defaults={'status': 'draft'}
            )

        messages.success(request, "Marks saved successfully.")
        return redirect(reverse('enter_exam_results') + f'?term={term_id}&course={class_id}&subject={subject_id}')

    students = []
    selected_term = None
    selected_class = None
    selected_subject = None
    subjects = []

    if term_id and class_id:
        selected_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
        selected_class = get_object_or_404(Course, id=class_id, school=school)
        subjects = Subject.objects.filter(course=selected_class).order_by('name')
        if subject_id:
            selected_subject = get_object_or_404(Subject, id=subject_id, course=selected_class)
            is_submitted = TeacherResultSubmission.objects.filter(
                staff=selected_subject.staff, subject=selected_subject,
                academic_term=selected_term, school_class=selected_class,
                status='submitted'
            ).exists()
            enrollments = StudentClassEnrollment.objects.filter(
                school_class=selected_class, status='active',
                student__admin__school=school
            ).filter(
                Q(term=selected_term) | Q(academic_year__academic_year=selected_term.academic_year)
            ).select_related('student__admin')
            for enr in enrollments:
                res = KNECReportCardResult.objects.filter(
                    student=enr.student, subject=selected_subject, academic_term=selected_term
                ).first()
                students.append({
                    'student': enr.student,
                    'result': res,
                })

    is_submitted = False
    if selected_term and selected_class and selected_subject:
        is_submitted = TeacherResultSubmission.objects.filter(
            staff=selected_subject.staff, subject=selected_subject,
            academic_term=selected_term, school_class=selected_class,
            status='submitted'
        ).exists()
    can_edit = not is_submitted or str(request.user.user_type) == '1'

    context = {
        'page_title': 'Enter Exam Results',
        'academic_terms': academic_terms,
        'courses': courses,
        'subjects': subjects,
        'all_subjects': all_subjects,
        'students': students,
        'selected_term': selected_term,
        'selected_class': selected_class,
        'selected_subject': selected_subject,
        'term_id': term_id,
        'class_id': class_id,
        'subject_id': subject_id,
        'is_submitted': is_submitted,
        'can_edit': can_edit,
        'is_admin': str(request.user.user_type) == '1',
    }
    return render(request, 'hod_template/enter_exam_results.html', context)


def delete_knec_result(request, result_id):
    """Delete a KNEC report card result (school-scoped)."""
    school = getattr(request, 'school', None)
    qs = KNECReportCardResult.objects.filter(student__admin__school=school) if school else KNECReportCardResult.objects.all()
    result = get_object_or_404(qs, id=result_id)
    term_id = result.academic_term_id
    class_id = request.GET.get('course') or request.GET.get('class')
    subject_id = result.subject_id
    result.delete()
    messages.success(request, "Result deleted successfully.")
    next_page = request.GET.get('next', 'enter_exam_results')
    redirect_url = reverse(next_page) + f'?term={term_id}&course={class_id}&subject={subject_id}'
    return redirect(redirect_url)


def teacher_submit_results(request):
    """Teacher submits results - locks marks. Only teacher for that subject can submit."""
    school = getattr(request, 'school', None)
    if not school:
        messages.warning(request, "School context required.")
        return redirect('admin_home')
    if request.user.user_type != '2' or not hasattr(request.user, 'staff'):
        messages.error(request, "Only teachers can submit results.")
        return redirect('enter_exam_results')
    staff = request.user.staff
    term_id = request.POST.get('academic_term')
    class_id = request.POST.get('school_class')
    subject_id = request.POST.get('subject')
    if not all([term_id, class_id, subject_id]):
        messages.error(request, "Missing term, class, or subject.")
        return redirect('enter_exam_results')
    academic_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    school_class = get_object_or_404(Course, id=class_id, school=school)
    subject = get_object_or_404(Subject, id=subject_id, course=school_class)
    if subject.staff_id != staff.id:
        messages.error(request, "You can only submit results for your own subjects.")
        return redirect('enter_exam_results')
    sub, created = TeacherResultSubmission.objects.get_or_create(
        staff=staff, subject=subject, academic_term=academic_term, school_class=school_class,
        defaults={'status': 'draft'}
    )
    if sub.status == 'submitted':
        messages.warning(request, "Results already submitted.")
    else:
        sub.status = 'submitted'
        sub.submitted_at = timezone.now()
        sub.save()
        messages.success(request, f"Results for {subject.name} submitted successfully. Marks are now locked.")
        # Notify school admins
        admin_users = CustomUser.objects.filter(user_type='1', school=school).exclude(is_superuser=True)
        results_link = reverse('result_submission_status') + f'?term={term_id}&course={class_id}'
        teacher_name = f"{staff.admin.first_name} {staff.admin.last_name}"
        for admin_user in admin_users:
            create_notification(
                admin_user,
                "Results Submitted",
                f"Teacher {teacher_name} submitted {subject.name} results for {school_class.name}.",
                results_link,
                school=school,
            )
    return redirect(reverse('enter_exam_results') + f'?term={term_id}&course={class_id}&subject={subject_id}')


def result_submission_status(request):
    """Admin only: View teacher submission status per term/class. Teachers enter marks and submit."""
    school = getattr(request, 'school', None)
    if not school:
        messages.warning(request, "School context required.")
        return redirect('admin_home')
    if str(request.user.user_type) != '1':
        messages.error(request, "Admin only.")
        return redirect('staff_home')
    academic_terms = AcademicTerm.objects.filter(school=school).order_by('-academic_year', 'term_name')
    courses = Course.objects.filter(school=school, is_active=True).order_by('name')
    term_id = request.GET.get('term')
    class_id = request.GET.get('course') or request.GET.get('class')
    status_rows = []
    selected_term = selected_class = None
    all_submitted = False
    if term_id and class_id:
        selected_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
        selected_class = get_object_or_404(Course, id=class_id, school=school)
        subjects = Subject.objects.filter(course=selected_class).select_related('staff__admin')
        for subj in subjects:
            sub = TeacherResultSubmission.objects.filter(
                subject=subj, academic_term=selected_term, school_class=selected_class
            ).first()
            status_rows.append({
                'subject': subj,
                'teacher': subj.staff,
                'submission': sub,
                'status': sub.status if sub else 'draft',
                'submitted_at': sub.submitted_at if sub else None,
            })
        all_submitted = all(r['status'] == 'submitted' for r in status_rows) if status_rows else False
    publish_status = None
    if selected_term:
        try:
            publish_status = selected_term.result_publish_status
        except Exception:
            pass
    is_admin = str(request.user.user_type) == '1'
    context = {
        'page_title': 'Result Submission Status',
        'academic_terms': academic_terms,
        'courses': courses,
        'status_rows': status_rows,
        'selected_term': selected_term,
        'selected_class': selected_class,
        'term_id': term_id,
        'class_id': class_id,
        'all_submitted': all_submitted,
        'is_published': publish_status.is_published if publish_status else False,
        'is_admin': is_admin,
    }
    return render(request, 'hod_template/result_submission_status.html', context)


def publish_term_results(request):
    """Admin only: Publish results for a term/class. Makes visible to parents/students."""
    school = getattr(request, 'school', None)
    if not school:
        return redirect('admin_home')
    if str(request.user.user_type) != '1':
        messages.error(request, "Admin only.")
        return redirect('admin_home')
    term_id = request.POST.get('academic_term')
    class_id = request.POST.get('school_class')
    if not term_id or not class_id:
        messages.error(request, "Missing term or class.")
        return redirect('result_submission_status')
    academic_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    school_class = get_object_or_404(Course, id=class_id, school=school)
    subjects = list(Subject.objects.filter(course=school_class))
    if not subjects:
        messages.error(request, "No subjects found for this class. Cannot publish.")
        return redirect(reverse('result_submission_status') + f'?term={term_id}&course={class_id}')
    all_submitted = all(
        TeacherResultSubmission.objects.filter(
            subject=s, academic_term=academic_term, school_class=school_class,
            status='submitted'
        ).exists()
        for s in subjects
    )
    if not all_submitted:
        draft_subjects = [
            s.name for s in subjects
            if not TeacherResultSubmission.objects.filter(
                subject=s, academic_term=academic_term, school_class=school_class,
                status='submitted'
            ).exists()
        ]
        messages.error(
            request,
            f"Some teachers have not submitted results yet: {', '.join(draft_subjects)}. "
            "All subjects must be submitted before publishing."
        )
        return redirect(reverse('result_submission_status') + f'?term={term_id}&course={class_id}')
    pub, _ = TermResultPublish.objects.get_or_create(
        academic_term=academic_term,
        defaults={'school': school, 'is_published': False}
    )
    pub.is_published = True
    pub.published_at = timezone.now()
    pub.published_by = request.user
    pub.school = school
    pub.save()

    # Notify parents of students in this class
    students = Student.objects.filter(course=school_class).select_related('admin')
    for student in students:
        for parent in Parent.objects.filter(children=student).select_related('admin'):
            create_notification(
                parent.admin,
                "Results Published",
                f"Term results for {academic_term} are now available. View {student.admin.first_name}'s report card.",
                reverse('parent_view_knec_report_card', args=[student.id, academic_term.id]),
                school=school,
            )

    messages.success(request, f"Results for {academic_term} published. Parents and students can now view.")
    return redirect(reverse('result_submission_status') + f'?term={term_id}&course={class_id}')


def unpublish_term_results(request):
    """Admin only: Unpublish results."""
    school = getattr(request, 'school', None)
    if not school or str(request.user.user_type) != '1':
        messages.error(request, "Admin only.")
        return redirect('admin_home')
    term_id = request.POST.get('academic_term')
    class_id = request.POST.get('school_class')
    if term_id and class_id:
        academic_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
        pub = getattr(academic_term, 'result_publish_status', None)
        if pub:
            pub.is_published = False
            pub.save()
            messages.success(request, "Results unpublished.")
    return redirect(reverse('result_submission_status') + f'?term={term_id}&course={class_id}')


def admin_unlock_teacher_submission(request):
    """Admin: Unlock submitted results so teacher can edit again."""
    school = getattr(request, 'school', None)
    if not school or str(request.user.user_type) != '1':
        messages.error(request, "Admin only.")
        return redirect('admin_home')
    submission_id = request.POST.get('submission_id')
    if submission_id:
        sub = TeacherResultSubmission.objects.filter(id=submission_id).first()
        if sub and sub.school_class.school_id == school.id:
            sub.status = 'draft'
            sub.submitted_at = None
            sub.save()
            messages.success(request, f"Unlocked {sub.subject.name} - {sub.staff.admin.get_full_name()}")
    term_id = request.POST.get('term_id')
    class_id = request.POST.get('class_id')
    return redirect(reverse('result_submission_status') + f'?term={term_id}&course={class_id}')


def enter_cat_marks(request):
    """MVP: Enter Continuous Assessment (CAT) marks"""
    active_term = AcademicTerm.get_active_term(school=getattr(request, 'school', None))
    if request.method == 'POST':
        if active_term and active_term.is_locked:
            messages.error(request, "Term is closed. CAT marks cannot be edited.")
            return redirect('enter_cat_marks')
        subject_id = request.POST.get('subject')
        assessment_name = request.POST.get('assessment_name', 'CAT 1')
        max_marks = float(request.POST.get('max_marks', 100))
        subject = get_object_or_404(Subject, id=subject_id)
        students = Student.objects.filter(course=subject.course)
        saved = 0
        for student in students:
            key = f'cat_{student.id}'
            if key in request.POST and request.POST[key]:
                marks = float(request.POST[key])
                ContinuousAssessment.objects.update_or_create(
                    student=student,
                    subject=subject,
                    term=active_term,
                    assessment_name=assessment_name,
                    defaults={'marks': marks, 'max_marks': max_marks, 'entered_by': request.user}
                )  # Multiple CATs per term: CAT 1, CAT 2, etc.
                saved += 1
        messages.success(request, f"Saved CAT marks for {saved} students")
        return redirect('enter_cat_marks')
    context = {
        'subjects': Subject.objects.all().select_related('course', 'staff'),
        'active_term': active_term,
        'page_title': 'Enter CAT Marks'
    }
    return render(request, 'hod_template/enter_cat_marks.html', context)


@csrf_exempt
def get_students_for_results(request):
    """AJAX: Get students for result entry"""
    subject_id = request.GET.get('subject_id')
    exam_schedule_id = request.GET.get('exam_schedule_id')
    if exam_schedule_id and request.user.user_type == '2':
        exam_schedule = ExamSchedule.objects.filter(id=exam_schedule_id).first()
        if exam_schedule and not exam_schedule.is_result_entry_allowed():
            return JsonResponse({'success': False, 'error': 'Result upload is closed for this exam.'})
    try:
        subject = Subject.objects.get(id=subject_id)
        students = Student.objects.filter(course=subject.course).select_related('admin')
        
        # Get existing results
        existing_results = {}
        if exam_schedule_id:
            results = ExamResult.objects.filter(
                subject=subject,
                exam_schedule_id=exam_schedule_id
            )
            existing_results = {r.student_id: {'marks': r.marks, 'comment': r.teacher_comment} for r in results}
        
        data = []
        for student in students:
            result_data = existing_results.get(student.id, {})
            data.append({
                'id': student.id,
                'name': str(student),
                'admission_number': student.admission_number,
                'marks': result_data.get('marks', ''),
                'comment': result_data.get('comment', '')
            })
        
        return JsonResponse({'success': True, 'students': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def view_exam_results(request):
    """View exam results by class/schedule"""
    exam_schedule_id = request.GET.get('exam_schedule')
    course_id = request.GET.get('course')
    
    results = []
    if exam_schedule_id and course_id:
        results = ExamResult.objects.filter(
            exam_schedule_id=exam_schedule_id,
            student__course_id=course_id
        ).select_related('student__admin', 'subject')
    
    context = {
        'exam_schedules': ExamSchedule.objects.filter(is_active=True),
        'courses': Course.objects.filter(is_active=True),
        'results': results,
        'selected_schedule': exam_schedule_id,
        'selected_course': course_id,
        'page_title': 'View Exam Results'
    }
    return render(request, 'hod_template/view_exam_results.html', context)


def print_result_slip(request, student_id, exam_schedule_id):
    """Generate individual result slip PDF"""
    student = get_object_or_404(Student, id=student_id)
    exam_schedule = get_object_or_404(ExamSchedule, id=exam_schedule_id)
    
    if not REPORTLAB_AVAILABLE:
        messages.error(request, 'PDF generation not available. Install reportlab.')
        return redirect('view_exam_results')
    
    results = ExamResult.objects.filter(
        student=student,
        exam_schedule=exam_schedule
    ).select_related('subject')
    
    # Calculate aggregates
    total_marks = sum(r.marks for r in results)
    total_subjects = results.count()
    average = total_marks / total_subjects if total_subjects > 0 else 0
    
    response = HttpResponse(content_type='application/pdf')
    filename = f"ResultSlip_{student.admission_number or student.id}_{exam_schedule.id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Header
    school = get_school_settings(school=getattr(request, 'school', None))
    title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER)
    elements.append(Paragraph(school.school_name, title_style))
    elements.append(Paragraph(f"{exam_schedule.name}", styles['Heading2']))
    elements.append(Paragraph("STUDENT RESULT SLIP", styles['Heading3']))
    elements.append(Spacer(1, 20))
    
    # Student Info
    info_data = [
        ['Student Name:', f"{student.admin.first_name} {student.admin.last_name}"],
        ['Admission No:', student.admission_number or 'N/A'],
        ['Class:', str(student.course) if student.course else 'N/A'],
        ['Term:', exam_schedule.get_term_display()],
        ['Session:', str(exam_schedule.session)],
    ]
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Results Table
    results_data = [['Subject', 'Marks', 'Grade', 'Points', 'Remarks']]
    total_points = 0
    for result in results:
        results_data.append([
            result.subject.name,
            f"{result.marks:.0f}",
            result.grade or '-',
            f"{result.points:.1f}",
            result.remarks or '-'
        ])
        total_points += result.points
    
    # Summary row
    from .grade_utils import get_mean_grade_from_points_school
    mean_grade = '-'
    if total_subjects > 0:
        mean_points = total_points / total_subjects
        school_obj = getattr(request, 'school', None) or (student.admin.school if student.admin_id else None)
        mean_grade = get_mean_grade_from_points_school(mean_points, school_obj)
    
    results_data.append(['Total', f"{total_marks:.0f}", '', f"{total_points:.1f}", ''])
    results_data.append(['Average', f"{average:.1f}", mean_grade, f"{total_points/total_subjects:.1f}" if total_subjects else '-', ''])
    
    results_table = Table(results_data, colWidths=[2.5*inch, 1*inch, 0.8*inch, 0.8*inch, 1.5*inch])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, -2), (-1, -1), colors.lightgrey),
    ]))
    elements.append(results_table)
    elements.append(Spacer(1, 30))
    
    # Comments
    elements.append(Paragraph("Class Teacher's Comment: ___________________________________", styles['Normal']))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("Principal's Comment: ______________________________________", styles['Normal']))
    elements.append(Spacer(1, 30))
    
    # Signatures
    sig_data = [['Class Teacher', 'Principal', 'Parent/Guardian']]
    sig_table = Table(sig_data, colWidths=[2*inch, 2*inch, 2*inch])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    return response


def bulk_print_result_slips(request):
    """Bulk print result slips for a class"""
    exam_schedule_id = request.GET.get('exam_schedule')
    course_id = request.GET.get('course')
    
    if not exam_schedule_id or not course_id:
        messages.error(request, "Select exam schedule and class")
        return redirect('view_exam_results')
    
    students = Student.objects.filter(course_id=course_id)
    
    # For now, redirect to individual print (in production, merge PDFs)
    messages.info(request, f"Printing result slips for {students.count()} students")
    return redirect('view_exam_results')


# ============================================
# CLASS ATTENDANCE VIEWS
# ============================================

def attendance_dashboard(request):
    """Attendance overview dashboard"""
    today = timezone.now().date()
    
    # Today's attendance stats
    todays_attendance = ClassAttendance.objects.filter(date=today)
    classes_marked = todays_attendance.count()
    
    # Recent attendance records
    recent_attendance = ClassAttendance.objects.select_related(
        'school_class', 'marked_by'
    ).order_by('-date')[:20]
    
    # Classes without attendance today
    all_classes = Course.objects.filter(is_active=True)
    marked_class_ids = todays_attendance.values_list('school_class_id', flat=True)
    classes_pending = all_classes.exclude(id__in=marked_class_ids)
    
    context = {
        'today': today,
        'classes_marked': classes_marked,
        'total_classes': all_classes.count(),
        'classes_pending': classes_pending,
        'recent_attendance': recent_attendance,
        'page_title': 'Attendance Dashboard'
    }
    return render(request, 'hod_template/attendance_dashboard.html', context)


def take_class_attendance(request):
    """Take daily class attendance. MVP: Blocked when term is closed."""
    if request.method == 'POST':
        active_term = AcademicTerm.get_active_term(school=getattr(request, 'school', None))
        if active_term and active_term.is_locked:
            messages.error(request, "Term is closed. Attendance cannot be edited.")
            return redirect('take_class_attendance')
        class_id = request.POST.get('school_class')
        date = request.POST.get('date')
        notify_parents = request.POST.get('notify_parents') == 'on'
        
        try:
            school_class = Course.objects.get(id=class_id)
            session = Session.objects.order_by('-start_year').first()
            staff = Staff.objects.filter(admin=request.user).first()
            
            # Create or get attendance record
            attendance, created = ClassAttendance.objects.get_or_create(
                school_class=school_class,
                date=date,
                defaults={
                    'session': session,
                    'marked_by': staff
                }
            )
            
            # Get students
            enrolled_students = Student.objects.filter(
                enrollments__school_class=school_class,
                enrollments__status='active'
            ).distinct()
            direct_students = Student.objects.filter(course=school_class)
            students = (enrolled_students | direct_students).distinct()
            
            absent_students = []
            
            for student in students:
                status_key = f'status_{student.id}'
                status = request.POST.get(status_key, 'absent')
                
                record, _ = ClassAttendanceRecord.objects.update_or_create(
                    class_attendance=attendance,
                    student=student,
                    defaults={'status': status}
                )
                
                if status == 'absent':
                    absent_students.append(student)
            
            attendance.is_completed = True
            attendance.save()
            
            # Send SMS for absent students
            if notify_parents and absent_students:
                for student in absent_students:
                    send_attendance_alert_sms(student, attendance.date, created_by=request.user)
                process_sms_queue()
                messages.info(request, f"Attendance SMS sent to parents of {len(absent_students)} absent students")
            
            messages.success(request, f"Attendance saved for {students.count()} students")
            return redirect('attendance_dashboard')
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    context = {
        'courses': Course.objects.filter(is_active=True).select_related('grade_level'),
        'today': timezone.now().date(),
        'page_title': 'Take Class Attendance'
    }
    return render(request, 'hod_template/take_class_attendance.html', context)


@csrf_exempt
def get_class_students_for_attendance(request):
    """AJAX: Get students for attendance marking (school-scoped)"""
    class_id = request.GET.get('class_id')
    date = request.GET.get('date')
    school = getattr(request, 'school', None)
    
    try:
        course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
        school_class = course_qs.get(id=class_id)
        
        # Get students
        enrolled = Student.objects.filter(
            enrollments__school_class=school_class,
            enrollments__status='active'
        ).distinct()
        direct = Student.objects.filter(course=school_class)
        students = (enrolled | direct).distinct().select_related('admin')
        
        # Check existing attendance
        existing_records = {}
        if date:
            attendance = ClassAttendance.objects.filter(
                school_class=school_class,
                date=date
            ).first()
            if attendance:
                records = ClassAttendanceRecord.objects.filter(class_attendance=attendance)
                existing_records = {r.student_id: r.status for r in records}
        
        data = []
        for student in students:
            data.append({
                'id': student.id,
                'name': str(student),
                'admission_number': student.admission_number or 'N/A',
                'status': existing_records.get(student.id, 'present')
            })
        
        return JsonResponse({'success': True, 'students': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def view_class_attendance(request, class_id):
    """View attendance for a specific class"""
    school = getattr(request, 'school', None)
    course_qs = Course.objects.filter(school=school) if school else Course.objects.all()
    school_class = get_object_or_404(course_qs, id=class_id)
    
    month = request.GET.get('month', timezone.now().month)
    year = request.GET.get('year', timezone.now().year)
    
    attendance_records = ClassAttendance.objects.filter(
        school_class=school_class,
        date__month=month,
        date__year=year
    ).prefetch_related('attendance_records__student')
    
    context = {
        'school_class': school_class,
        'attendance_records': attendance_records,
        'month': month,
        'year': year,
        'page_title': f'Attendance - {school_class}'
    }
    return render(request, 'hod_template/view_class_attendance.html', context)


def delete_class_attendance(request, attendance_id):
    """Delete a class attendance record (whole day's attendance)."""
    school = getattr(request, 'school', None)
    qs = ClassAttendance.objects.filter(school_class__school=school) if school else ClassAttendance.objects.all()
    attendance = get_object_or_404(qs, id=attendance_id)
    class_id = attendance.school_class_id
    attendance.delete()
    messages.success(request, "Attendance record deleted successfully.")
    return redirect('view_class_attendance', class_id=class_id)


def student_attendance_report(request, student_id):
    """View attendance report for a student"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    
    records = ClassAttendanceRecord.objects.filter(
        student=student
    ).select_related('class_attendance__school_class').order_by('-class_attendance__date')
    
    # Calculate summary
    total = records.count()
    present = records.filter(status='present').count()
    absent = records.filter(status='absent').count()
    late = records.filter(status='late').count()
    percentage = (present / total * 100) if total > 0 else 0
    
    context = {
        'student': student,
        'records': records,
        'total': total,
        'present': present,
        'absent': absent,
        'late': late,
        'percentage': round(percentage, 1),
        'page_title': f'Attendance Report - {student}'
    }
    return render(request, 'hod_template/student_attendance_report.html', context)


# ============================================
# SCHOOL SETTINGS VIEW
# ============================================

def school_settings(request):
    """Manage school settings"""
    settings_obj = get_school_settings(school=getattr(request, 'school', None))
    
    if request.method == 'POST':
        form = SchoolSettingsForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated successfully")
            return redirect('school_settings')
    else:
        form = SchoolSettingsForm(instance=settings_obj)
    
    context = {
        'form': form,
        'settings': settings_obj,
        'page_title': 'School Settings'
    }
    return render(request, 'hod_template/school_settings.html', context)


# ============================================
# STUDENT DETAIL PAGE - with tabs (General, Fee Payment, Exam Results, SMS Messages)
# ============================================

def student_detail(request, student_id):
    """Student detail page - redirects to General tab"""
    return redirect('student_detail_general', student_id=student_id)


def student_detail_general(request, student_id):
    """Student detail - General tab with basic info and guardians"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    guardians = student.guardians.all()
    
    # Get class info
    class_info = student.get_class_info()
    stream = class_info.stream if class_info and hasattr(class_info, 'stream') else None
    
    context = {
        'student': student,
        'guardians': guardians,
        'class_info': class_info,
        'stream': stream,
        'active_tab': 'general',
        'page_title': f'{student.admin.first_name} {student.admin.last_name}'
    }
    return render(request, 'hod_template/student_detail_general.html', context)


def student_detail_fees(request, student_id):
    """Student detail - Fee Payment tab"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    
    # Get fee payments for this student
    payments = FeePayment.objects.filter(student=student).order_by('-created_at')
    
    # Calculate totals
    total_billed = student.total_fee_billed
    total_paid = student.get_total_paid()
    balance = total_billed - total_paid
    
    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(payments, 10)
    try:
        payments = paginator.page(page)
    except:
        payments = paginator.page(1)
    
    context = {
        'student': student,
        'payments': payments,
        'total_billed': total_billed,
        'total_paid': total_paid,
        'balance': balance,
        'active_tab': 'fees',
        'page_title': f'Fee Payment - {student}'
    }
    return render(request, 'hod_template/student_detail_fees.html', context)


def student_add_fee_payment(request, student_id):
    """Add new fee payment for student"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            payment_date = request.POST.get('payment_date')
            payment_mode = request.POST.get('payment_mode', 'cash')
            transaction_type = request.POST.get('transaction_type', 'credit')
            description = request.POST.get('description', '')
            paid_by = request.POST.get('paid_by', '')
            
            # Generate receipt number
            settings_obj = get_school_settings(school=getattr(request, 'school', None))
            receipt_number = settings_obj.get_next_receipt_number() + '-' + student.admission_number
            
            # Get current session
            session = Session.objects.order_by('-start_year').first()
            
            # Create payment
            payment = FeePayment.objects.create(
                student=student,
                session=session,
                amount=amount,
                payment_mode=payment_mode,
                transaction_type=transaction_type,
                receipt_number=receipt_number,
                payment_date=payment_date,
                received_by=request.user,
                paid_by=paid_by,
                description=description
            )
            
            # Notify parent(s) of the student
            school = getattr(request, 'school', None)
            for parent in Parent.objects.filter(children=student).select_related('admin'):
                create_notification(
                    parent.admin,
                    "Fee Payment Received",
                    f"Payment of KES {amount:,.2f} recorded for {student.admin.first_name} {student.admin.last_name}. Receipt: {receipt_number}",
                    reverse('parent_view_child_fees', args=[student.id]),
                    school=school,
                )
            
            messages.success(request, f"Payment of KES {amount:,.2f} recorded successfully. Receipt: {receipt_number}")
            return redirect('student_detail_fees', student_id=student_id)
            
        except Exception as e:
            messages.error(request, f"Error recording payment: {str(e)}")
    
    return redirect('student_detail_fees', student_id=student_id)


def student_edit_fee_payment(request, student_id, payment_id):
    """Edit fee payment"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    payment = get_object_or_404(FeePayment, id=payment_id, student=student)
    
    if request.method == 'POST':
        try:
            payment.amount = Decimal(request.POST.get('amount', payment.amount))
            payment.payment_mode = request.POST.get('payment_mode', payment.payment_mode)
            payment.transaction_type = request.POST.get('transaction_type', payment.transaction_type)
            payment.description = request.POST.get('description', payment.description)
            payment.save()
            
            messages.success(request, "Payment updated successfully")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return redirect('student_detail_fees', student_id=student_id)


def student_delete_fee_payment(request, student_id, payment_id):
    """Delete fee payment"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    payment = get_object_or_404(FeePayment, id=payment_id, student=student)
    
    if request.method == 'POST':
        payment.is_reversed = True
        payment.reversal_reason = "Deleted by admin"
        payment.save()
        messages.success(request, "Payment deleted successfully")
    
    return redirect('student_detail_fees', student_id=student_id)


def student_print_fee_receipt(request, student_id, payment_id):
    """Print fee receipt for a specific payment"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    payment = get_object_or_404(FeePayment, id=payment_id, student=student)
    settings_obj = get_school_settings(school=getattr(request, 'school', None))
    
    # Create PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="receipt-{payment.receipt_number}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # School Header
    header_style = ParagraphStyle('Header', parent=styles['Heading1'], alignment=1, fontSize=16)
    sub_header_style = ParagraphStyle('SubHeader', parent=styles['Normal'], alignment=1, fontSize=10)
    
    elements.append(Paragraph(f"<b>{settings_obj.school_name}</b>", header_style))
    if settings_obj.school_address:
        elements.append(Paragraph(settings_obj.school_address, sub_header_style))
    if settings_obj.school_phone:
        elements.append(Paragraph(f"Phone: {settings_obj.school_phone}", sub_header_style))
    
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Fee Payment Receipt</b>", ParagraphStyle('Title', parent=styles['Heading2'], alignment=1)))
    elements.append(Spacer(1, 15))
    
    # Receipt details table
    class_info = student.get_class_info()
    stream = class_info.stream.name if class_info and class_info.stream else '-'
    
    balance = student.get_fee_balance()
    
    data = [
        ['Student Name:', f'{student.admin.first_name} {student.admin.last_name}', 'Admission No:', student.admission_number or '-'],
        ['Class:', str(class_info) if class_info else '-', 'Section:', stream],
        ['Receipt No:', payment.receipt_number, 'Payment Date:', payment.payment_date.strftime('%d-%b-%Y %I:%M %p') if payment.payment_date else '-'],
        ['Payment Method:', payment.get_payment_mode_display(), 'Transaction Type:', payment.get_transaction_type_display()],
        ['Amount (KES):', f'{payment.amount:,.2f}', 'Fee Balance (KES):', f'{balance:,.2f}'],
        ['Paid By:', payment.paid_by or '-', 'Description:', payment.description or '-'],
    ]
    
    table = Table(data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.9, 0.9, 0.9)),
        ('BACKGROUND', (2, 0), (2, -1), colors.Color(0.9, 0.9, 0.9)),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    
    elements.append(Spacer(1, 40))
    
    # Signature line
    elements.append(Paragraph("_" * 40, styles['Normal']))
    elements.append(Paragraph("<b>Headteacher / Finance Officer</b>", ParagraphStyle('Sig', parent=styles['Normal'], fontSize=10)))
    
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<i>Printed On: {timezone.now().strftime('%d-%b-%Y %I:%M %p')}</i>", ParagraphStyle('Footer', parent=styles['Normal'], alignment=2, fontSize=8)))
    elements.append(Paragraph("<i>Thank you for your payment. Keep this receipt for your records.</i>", ParagraphStyle('Footer', parent=styles['Normal'], alignment=1, fontSize=8)))
    
    doc.build(elements)
    return response


def student_print_fee_statement(request, student_id):
    """Print fee statement for student"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    settings_obj = get_school_settings(school=getattr(request, 'school', None))
    
    payments = FeePayment.objects.filter(student=student, is_reversed=False).order_by('-created_at')
    total_billed = student.total_fee_billed
    total_paid = student.get_total_paid()
    balance = total_billed - total_paid
    
    # Create PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="statement-{student.admission_number}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Header
    header_style = ParagraphStyle('Header', parent=styles['Heading1'], alignment=1, fontSize=16)
    elements.append(Paragraph(f"<b>{settings_obj.school_name}</b>", header_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("<b>Fee Statement</b>", ParagraphStyle('Title', parent=styles['Heading2'], alignment=1)))
    elements.append(Spacer(1, 15))
    
    # Student info
    class_info = student.get_class_info()
    info_data = [
        ['Student:', f'{student.admin.first_name} {student.admin.last_name}'],
        ['Admission No:', student.admission_number or '-'],
        ['Class:', str(class_info) if class_info else '-'],
        ['Date:', timezone.now().strftime('%d-%b-%Y')],
    ]
    info_table = Table(info_data, colWidths=[1.5*inch, 3*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Summary
    summary_data = [
        ['Total Fee Billed:', f'KES {total_billed:,.2f}'],
        ['Total Paid:', f'KES {total_paid:,.2f}'],
        ['Balance:', f'KES {balance:,.2f}'],
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Payment history
    elements.append(Paragraph("<b>Payment History</b>", styles['Heading3']))
    
    if payments:
        payment_data = [['#', 'Receipt No', 'Date', 'Method', 'Amount']]
        for i, p in enumerate(payments[:20], 1):
            payment_data.append([
                str(i),
                p.receipt_number,
                p.payment_date.strftime('%d/%m/%Y') if p.payment_date else '-',
                p.get_payment_mode_display(),
                f'KES {p.amount:,.2f}'
            ])
        
        payment_table = Table(payment_data, colWidths=[0.5*inch, 2*inch, 1.5*inch, 1*inch, 1.5*inch])
        payment_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.8, 0.8, 0.8)),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ]))
        elements.append(payment_table)
    else:
        elements.append(Paragraph("No payments recorded.", styles['Normal']))
    
    doc.build(elements)
    return response


def student_detail_results(request, student_id):
    """Student detail - Exam Results tab"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    
    # Get filters
    academic_year_id = request.GET.get('academic_year')
    term = request.GET.get('term')
    exam_type_id = request.GET.get('exam_type')
    subject_id = request.GET.get('subject')
    
    # Get results
    results = StudentExamResult.objects.filter(student=student).select_related(
        'academic_year', 'exam_type', 'subject'
    )
    
    if academic_year_id:
        results = results.filter(academic_year_id=academic_year_id)
    if term:
        results = results.filter(term=term)
    if exam_type_id:
        results = results.filter(exam_type_id=exam_type_id)
    if subject_id:
        results = results.filter(subject_id=subject_id)
    
    results = results.order_by('-academic_year__start_year', 'term', 'subject__name')
    
    context = {
        'student': student,
        'results': results,
        'sessions': Session.objects.all().order_by('-start_year'),
        'exam_types': ExamType.objects.filter(is_active=True),
        'subjects': Subject.objects.all(),
        'selected_year': academic_year_id,
        'selected_term': term,
        'selected_exam_type': exam_type_id,
        'selected_subject': subject_id,
        'active_tab': 'results',
        'page_title': f'Exam Results for {student}'
    }
    return render(request, 'hod_template/student_detail_results.html', context)


def student_add_result(request, student_id):
    """Add exam result for student"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    
    if request.method == 'POST':
        try:
            academic_year_id = request.POST.get('academic_year')
            term = request.POST.get('term')
            exam_type_id = request.POST.get('exam_type')
            subject_id = request.POST.get('subject')
            score = float(request.POST.get('score', 0))
            out_of = float(request.POST.get('out_of', 100))
            
            result, created = StudentExamResult.objects.update_or_create(
                student=student,
                academic_year_id=academic_year_id,
                term=term,
                exam_type_id=exam_type_id,
                subject_id=subject_id,
                defaults={
                    'score': score,
                    'out_of': out_of,
                    'entered_by': request.user
                }
            )
            
            if created:
                messages.success(request, "Result added successfully")
            else:
                messages.success(request, "Result updated successfully")
                
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return redirect('student_detail_results', student_id=student_id)


def student_edit_result(request, student_id, result_id):
    """Edit exam result"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    result = get_object_or_404(StudentExamResult, id=result_id, student=student)
    
    if request.method == 'POST':
        try:
            result.score = float(request.POST.get('score', result.score))
            result.out_of = float(request.POST.get('out_of', result.out_of))
            result.grade = None  # Reset to recalculate
            result.save()
            
            messages.success(request, "Result updated successfully")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return redirect('student_detail_results', student_id=student_id)


def student_delete_result(request, student_id, result_id):
    """Delete exam result"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    result = get_object_or_404(StudentExamResult, id=result_id, student=student)
    
    if request.method == 'POST':
        result.delete()
        messages.success(request, "Result deleted successfully")
    
    return redirect('student_detail_results', student_id=student_id)


def student_detail_sms(request, student_id):
    """Student detail - SMS Messages tab"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    guardians = student.guardians.all()
    
    # Get SMS history for this student
    sms_messages = StudentSMS.objects.filter(student=student).order_by('-created_at')
    
    context = {
        'student': student,
        'guardians': guardians,
        'sms_messages': sms_messages,
        'active_tab': 'sms',
        'page_title': f'SMS Messages - {student}'
    }
    return render(request, 'hod_template/student_detail_sms.html', context)


def student_send_sms(request, student_id):
    """Send SMS to student's guardian"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        message = request.POST.get('message')
        guardian_id = request.POST.get('guardian_id')
        
        try:
            guardian = Guardian.objects.get(id=guardian_id) if guardian_id else None
            
            # Create SMS record
            sms_record = StudentSMS.objects.create(
                student=student,
                guardian=guardian,
                phone_number=phone_number,
                message=message,
                sent_by=request.user,
                delivery_status='pending'
            )
            
            # Add to SMS queue for sending
            from .sms_service import add_to_sms_queue, process_sms_queue
            add_to_sms_queue(
                phone_number=phone_number,
                message=message,
                recipient_type='guardian',
                recipient_id=guardian.id if guardian else None,
                created_by=request.user
            )
            
            # Process queue (send immediately)
            result = process_sms_queue(batch_size=1)
            
            if result['success'] > 0:
                sms_record.delivery_status = 'sent'
                sms_record.delivery_time = timezone.now()
                sms_record.save()
                messages.success(request, f"SMS sent successfully to {phone_number}")
            else:
                sms_record.delivery_status = 'failed'
                sms_record.error_message = "Failed to send"
                sms_record.save()
                messages.warning(request, "SMS queued but may not have been delivered")
                
        except Exception as e:
            messages.error(request, f"Error sending SMS: {str(e)}")
    
    return redirect('student_detail_sms', student_id=student_id)


def student_add_guardian(request, student_id):
    """Add guardian for student"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            phone_number = request.POST.get('phone_number')
            relationship = request.POST.get('relationship', 'guardian')
            email = request.POST.get('email', '')
            is_primary = request.POST.get('is_primary') == 'on'
            
            # If this is primary, unset others
            if is_primary:
                student.guardians.update(is_primary=False)
            
            Guardian.objects.create(
                student=student,
                name=name,
                phone_number=phone_number,
                relationship=relationship,
                email=email if email else None,
                is_primary=is_primary
            )
            
            messages.success(request, f"Guardian {name} added successfully")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return redirect('student_detail_general', student_id=student_id)


def student_edit_guardian(request, student_id, guardian_id):
    """Edit guardian"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    guardian = get_object_or_404(Guardian, id=guardian_id, student=student)
    
    if request.method == 'POST':
        try:
            guardian.name = request.POST.get('name', guardian.name)
            guardian.phone_number = request.POST.get('phone_number', guardian.phone_number)
            guardian.relationship = request.POST.get('relationship', guardian.relationship)
            guardian.email = request.POST.get('email') or None
            is_primary = request.POST.get('is_primary') == 'on'
            
            if is_primary and not guardian.is_primary:
                student.guardians.update(is_primary=False)
            guardian.is_primary = is_primary
            guardian.save()
            
            messages.success(request, "Guardian updated successfully")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return redirect('student_detail_general', student_id=student_id)


def student_delete_guardian(request, student_id, guardian_id):
    """Delete guardian"""
    school = getattr(request, 'school', None)
    qs = Student.objects.filter(admin__school=school) if school else Student.objects.all()
    student = get_object_or_404(qs, id=student_id)
    guardian = get_object_or_404(Guardian, id=guardian_id, student=student)
    
    if request.method == 'POST':
        guardian.delete()
        messages.success(request, "Guardian deleted successfully")
    
    return redirect('student_detail_general', student_id=student_id)


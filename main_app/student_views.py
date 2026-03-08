import json
import math
from datetime import datetime

from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (HttpResponseRedirect, get_object_or_404,
                              redirect, render)
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .forms import *
from .models import *
from .models import Timetable, Homework, HomeworkSubmission, Announcement


def student_home(request):
    try:
        student = Student.objects.get(admin=request.user)
    except Student.DoesNotExist:
        from django.contrib.auth import logout
        from django.contrib import messages
        logout(request)
        messages.error(request, "Your student profile was not found. Please contact the administrator.")
        return redirect(reverse('login_page'))
    total_subject = Subject.objects.filter(course=student.course).count()
    total_attendance = AttendanceReport.objects.filter(student=student).count()
    total_present = AttendanceReport.objects.filter(student=student, status=True).count()
    if total_attendance == 0:  # Don't divide. DivisionByZero
        percent_absent = percent_present = 0
    else:
        percent_present = math.floor((total_present/total_attendance) * 100)
        percent_absent = math.ceil(100 - percent_present)
    subject_name = []
    data_present = []
    data_absent = []
    subjects = Subject.objects.filter(course=student.course)
    for subject in subjects:
        attendance = Attendance.objects.filter(subject=subject)
        present_count = AttendanceReport.objects.filter(
            attendance__in=attendance, status=True, student=student).count()
        absent_count = AttendanceReport.objects.filter(
            attendance__in=attendance, status=False, student=student).count()
        subject_name.append(subject.name)
        data_present.append(present_count)
        data_absent.append(absent_count)
    context = {
        'total_attendance': total_attendance,
        'percent_present': percent_present,
        'percent_absent': percent_absent,
        'total_subject': total_subject,
        'subjects': subjects,
        'data_present': data_present,
        'data_absent': data_absent,
        'data_name': subject_name,
        'page_title': 'Student Homepage'

    }
    return render(request, 'student_template/home_content.html', context)


@ csrf_exempt
def student_view_attendance(request):
    student = get_object_or_404(Student, admin=request.user)
    if request.method != 'POST':
        course = get_object_or_404(Course, id=student.course.id)
        context = {
            'subjects': Subject.objects.filter(course=course),
            'page_title': 'View Attendance'
        }
        return render(request, 'student_template/student_view_attendance.html', context)
    else:
        subject_id = request.POST.get('subject')
        start = request.POST.get('start_date')
        end = request.POST.get('end_date')
        try:
            subject = get_object_or_404(Subject, id=subject_id)
            start_date = datetime.strptime(start, "%Y-%m-%d")
            end_date = datetime.strptime(end, "%Y-%m-%d")
            attendance = Attendance.objects.filter(
                date__range=(start_date, end_date), subject=subject)
            attendance_reports = AttendanceReport.objects.filter(
                attendance__in=attendance, student=student)
            json_data = []
            for report in attendance_reports:
                data = {
                    "date":  str(report.attendance.date),
                    "status": report.status
                }
                json_data.append(data)
            return JsonResponse(json_data, safe=False)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


def student_apply_leave(request):
    form = LeaveReportStudentForm(request.POST or None)
    student = get_object_or_404(Student, admin_id=request.user.id)
    context = {
        'form': form,
        'leave_history': LeaveReportStudent.objects.filter(student=student),
        'page_title': 'Apply for leave'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.student = student
                obj.save()
                messages.success(
                    request, "Application for leave has been submitted for review")
                return redirect(reverse('student_apply_leave'))
            except Exception:
                messages.error(request, "Could not submit")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "student_template/student_apply_leave.html", context)


def student_feedback(request):
    form = FeedbackStudentForm(request.POST or None)
    student = get_object_or_404(Student, admin_id=request.user.id)
    context = {
        'form': form,
        'feedbacks': FeedbackStudent.objects.filter(student=student),
        'page_title': 'Student Feedback'

    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.student = student
                obj.save()
                messages.success(
                    request, "Feedback submitted for review")
                return redirect(reverse('student_feedback'))
            except Exception:
                messages.error(request, "Could not Submit!")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "student_template/student_feedback.html", context)


def student_view_profile(request):
    student = get_object_or_404(Student, admin=request.user)
    form = StudentEditForm(request.POST or None, request.FILES or None,
                           instance=student)
    context = {'form': form,
               'page_title': 'View/Edit Profile'
               }
    if request.method == 'POST':
        try:
            if form.is_valid():
                first_name = form.cleaned_data.get('first_name')
                last_name = form.cleaned_data.get('last_name')
                password = form.cleaned_data.get('password') or None
                address = form.cleaned_data.get('address')
                gender = form.cleaned_data.get('gender')
                passport = request.FILES.get('profile_pic') or None
                admin = student.admin
                if password != None:
                    admin.set_password(password)
                if passport != None:
                    fs = FileSystemStorage()
                    filename = fs.save(passport.name, passport)
                    passport_url = fs.url(filename)
                    admin.profile_pic = passport_url
                admin.first_name = first_name
                admin.last_name = last_name
                admin.address = address
                admin.gender = gender
                admin.save()
                student.save()
                messages.success(request, "Profile Updated!")
                return redirect(reverse('student_view_profile'))
            else:
                messages.error(request, "Invalid Data Provided")
        except Exception as e:
            messages.error(request, "Error Occured While Updating Profile " + str(e))

    return render(request, "student_template/student_view_profile.html", context)


@csrf_exempt
def student_fcmtoken(request):
    token = request.POST.get('token')
    student_user = get_object_or_404(CustomUser, id=request.user.id)
    try:
        student_user.fcm_token = token
        student_user.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def student_view_notification(request):
    student = get_object_or_404(Student, admin=request.user)
    notifications = NotificationStudent.objects.filter(student=student)
    context = {
        'notifications': notifications,
        'page_title': "View Notifications"
    }
    return render(request, "student_template/student_view_notification.html", context)


def student_view_result(request):
    student = get_object_or_404(Student, admin=request.user)
    results = StudentResult.objects.filter(student=student)
    context = {
        'results': results,
        'page_title': "View Results"
    }
    return render(request, "student_template/student_view_result.html", context)


def student_view_fees(request):
    """Student view their fees outstanding"""
    student = get_object_or_404(Student, admin=request.user)
    fees = StudentFees.objects.filter(student=student).order_by('-session__id')
    context = {
        'fees': fees,
        'page_title': "My Fees"
    }
    return render(request, "student_template/student_view_fees.html", context)


def student_view_timetable(request):
    """Student view their class timetable"""
    student = get_object_or_404(Student, admin=request.user)
    timetables = Timetable.objects.filter(course=student.course).select_related(
        'subject', 'staff__admin'
    ).order_by('day', 'start_time')
    
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    timetable_by_day = {day: [] for day in days}
    for tt in timetables:
        if tt.day in timetable_by_day:
            timetable_by_day[tt.day].append(tt)
    
    context = {
        'timetable_by_day': timetable_by_day,
        'days': days,
        'page_title': "My Timetable"
    }
    return render(request, "student_template/student_view_timetable.html", context)


def student_view_homework(request):
    """Student view assigned homework"""
    student = get_object_or_404(Student, admin=request.user)
    homework_list = Homework.objects.filter(course=student.course).select_related(
        'subject', 'staff__admin'
    ).order_by('-due_date')
    
    homework_data = []
    for hw in homework_list:
        submission = HomeworkSubmission.objects.filter(homework=hw, student=student).first()
        homework_data.append({
            'homework': hw,
            'submission': submission,
            'status': 'Submitted' if submission else ('Graded' if submission and submission.graded_at else 'Pending')
        })
    
    context = {
        'homework_data': homework_data,
        'page_title': "My Homework"
    }
    return render(request, "student_template/student_view_homework.html", context)


def student_submit_homework(request, homework_id):
    """Student submit homework"""
    student = get_object_or_404(Student, admin=request.user)
    homework = get_object_or_404(Homework, id=homework_id, course=student.course)
    
    # Check if already submitted
    existing_submission = HomeworkSubmission.objects.filter(homework=homework, student=student).first()
    
    if request.method == 'POST':
        submission_text = request.POST.get('submission_text')
        submission_file = request.FILES.get('submission_file')
        
        try:
            if existing_submission:
                existing_submission.submission_text = submission_text
                if submission_file:
                    existing_submission.submission_file = submission_file
                existing_submission.save()
                messages.success(request, "Homework submission updated!")
            else:
                HomeworkSubmission.objects.create(
                    homework=homework,
                    student=student,
                    submission_text=submission_text,
                    submission_file=submission_file
                )
                messages.success(request, "Homework submitted successfully!")
            return redirect(reverse('student_view_homework'))
        except Exception as e:
            messages.error(request, f"Error submitting homework: {str(e)}")
    
    context = {
        'homework': homework,
        'existing_submission': existing_submission,
        'page_title': f"Submit - {homework.title}"
    }
    return render(request, "student_template/student_submit_homework.html", context)


def student_view_announcements(request):
    """Student view announcements"""
    student = get_object_or_404(Student, admin=request.user)
    school = getattr(request, 'school', None)
    
    from django.db.models import Q
    announcements = Announcement.objects.filter(
        Q(target_audience='all') | 
        Q(target_audience='students') |
        Q(target_audience='class', target_course=student.course),
        is_active=True
    )
    if school:
        announcements = announcements.filter(created_by__school=school)
    announcements = announcements.order_by('-publish_date')
    
    context = {
        'announcements': announcements,
        'page_title': "Announcements"
    }
    return render(request, "student_template/student_view_announcements.html", context)


# ============================================================
# CLASS INFO FOR STUDENTS
# ============================================================

def student_view_class_info(request):
    """Student view their class information"""
    from .models import StudentClassEnrollment
    
    student = get_object_or_404(Student, admin=request.user)
    
    # Get current enrollment
    current_enrollment = StudentClassEnrollment.objects.filter(
        student=student,
        status='active'
    ).select_related(
        'school_class__grade_level', 
        'school_class__stream',
        'school_class__class_teacher__admin',
        'academic_year'
    ).first()
    
    # Get class info (use current_class or course for backward compatibility)
    school_class = None
    if current_enrollment:
        school_class = current_enrollment.school_class
    elif student.current_class:
        school_class = student.current_class
    elif student.course:
        school_class = student.course
    
    # Get class teacher
    class_teacher = None
    if school_class and school_class.class_teacher:
        class_teacher = school_class.class_teacher
    
    # Get enrollment history
    enrollment_history = StudentClassEnrollment.objects.filter(
        student=student
    ).select_related(
        'school_class__grade_level',
        'school_class__stream',
        'academic_year'
    ).order_by('-academic_year__start_year')
    
    context = {
        'student': student,
        'current_enrollment': current_enrollment,
        'school_class': school_class,
        'class_teacher': class_teacher,
        'enrollment_history': enrollment_history,
        'page_title': "My Class"
    }
    return render(request, "student_template/student_view_class_info.html", context)


def student_view_classmates(request):
    """Student view their classmates"""
    from .models import StudentClassEnrollment
    
    student = get_object_or_404(Student, admin=request.user)
    school = getattr(request, 'school', None)
    
    # Get student's current class
    school_class = student.current_class or student.course
    
    if not school_class:
        messages.error(request, "You are not enrolled in any class")
        return redirect(reverse('student_home'))
    
    # Get classmates from enrollments
    enrollments_qs = StudentClassEnrollment.objects.filter(
        school_class=school_class,
        status='active'
    )
    if school:
        enrollments_qs = enrollments_qs.filter(school_class__school=school)
    enrollments = enrollments_qs.select_related('student__admin').exclude(student=student)
    
    # Also get students directly assigned (backward compatibility)
    from django.db.models import Q
    direct_classmates_qs = Student.objects.filter(
        Q(course=school_class) | Q(current_class=school_class)
    ).exclude(id=student.id)
    if school:
        direct_classmates_qs = direct_classmates_qs.filter(admin__school=school)
    direct_classmates = direct_classmates_qs.select_related('admin')
    
    context = {
        'school_class': school_class,
        'enrollments': enrollments,
        'direct_classmates': direct_classmates,
        'page_title': f"Classmates - {school_class}"
    }
    return render(request, "student_template/student_view_classmates.html", context)

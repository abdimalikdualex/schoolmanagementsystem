import json

from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (HttpResponseRedirect, get_object_or_404,redirect, render)
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from django.db import models
from django.db.models import Q

from .forms import *
from .models import *
from .models import Homework, HomeworkSubmission, Timetable, Message, Parent, StudentClassEnrollment


def staff_home(request):
    staff = get_object_or_404(Staff, admin=request.user)
    total_students = Student.objects.filter(course=staff.course).count()
    total_leave = LeaveReportStaff.objects.filter(staff=staff).count()
    subjects = Subject.objects.filter(staff=staff)
    total_subject = subjects.count()
    attendance_list = Attendance.objects.filter(subject__in=subjects)
    total_attendance = attendance_list.count()
    attendance_list = []
    subject_list = []
    for subject in subjects:
        attendance_count = Attendance.objects.filter(subject=subject).count()
        subject_list.append(subject.name)
        attendance_list.append(attendance_count)
    context = {
        'page_title': 'Staff Panel - ' + str(staff.admin.last_name) + ' (' + str(staff.course) + ')',
        'total_students': total_students,
        'total_attendance': total_attendance,
        'total_leave': total_leave,
        'total_subject': total_subject,
        'subject_list': subject_list,
        'attendance_list': attendance_list
    }
    return render(request, 'staff_template/home_content.html', context)


def staff_take_attendance(request):
    staff = get_object_or_404(Staff, admin=request.user)
    subjects = Subject.objects.filter(staff_id=staff)
    sessions = Session.objects.all()
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'page_title': 'Take Attendance'
    }

    return render(request, 'staff_template/staff_take_attendance.html', context)


@csrf_exempt
def get_students(request):
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    if not subject_id or not session_id:
        return JsonResponse([], safe=False)
    # MVP: Block if result entry is closed for this session
    from .result_entry_permissions import can_teacher_enter_legacy_results
    if not request.user.is_superuser and request.user.user_type != '1':
        if not can_teacher_enter_legacy_results(request, session_id):
            return JsonResponse({'error': 'Result upload is currently closed. Please contact the administrator.'}, status=403)
    try:
        subject = get_object_or_404(Subject, id=subject_id)
        session = get_object_or_404(Session, id=session_id)
        course = subject.course
        if not course:
            return JsonResponse([], safe=False)
        # Find students: legacy (course+session) OR via StudentClassEnrollment
        students = Student.objects.filter(
            Q(course=course, session=session) |
            Q(enrollments__school_class=course, enrollments__academic_year=session, enrollments__status='active')
        ).distinct()
        student_data = []
        for student in students:
            data = {
                "id": student.id,
                "name": student.admin.last_name + " " + student.admin.first_name
            }
            student_data.append(data)
        return JsonResponse(student_data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def save_attendance(request):
    student_data = request.POST.get('student_ids')
    date = request.POST.get('date')
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    if not student_data:
        return JsonResponse({'error': 'No student data provided'}, status=400)
    try:
        students = json.loads(student_data)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid student data format'}, status=400)
    try:
        session = get_object_or_404(Session, id=session_id)
        subject = get_object_or_404(Subject, id=subject_id)
        attendance = Attendance(session=session, subject=subject, date=date)
        attendance.save()

        for student_dict in students:
            student = get_object_or_404(Student, id=student_dict.get('id'))
            attendance_report = AttendanceReport(student=student, attendance=attendance, status=student_dict.get('status'))
            attendance_report.save()
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'status': 'OK'})


def staff_update_attendance(request):
    staff = get_object_or_404(Staff, admin=request.user)
    subjects = Subject.objects.filter(staff_id=staff)
    sessions = Session.objects.all()
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'page_title': 'Update Attendance'
    }

    return render(request, 'staff_template/staff_update_attendance.html', context)


@csrf_exempt
def get_student_attendance(request):
    attendance_date_id = request.POST.get('attendance_date_id')
    try:
        date = get_object_or_404(Attendance, id=attendance_date_id)
        attendance_data = AttendanceReport.objects.filter(attendance=date)
        student_data = []
        for attendance in attendance_data:
            data = {"id": attendance.student.admin.id,
                    "name": attendance.student.admin.last_name + " " + attendance.student.admin.first_name,
                    "status": attendance.status}
            student_data.append(data)
        return JsonResponse(student_data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def update_attendance(request):
    student_data = request.POST.get('student_ids')
    date = request.POST.get('date')
    if not student_data:
        return JsonResponse({'error': 'No student data provided'}, status=400)
    try:
        students = json.loads(student_data)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid student data format'}, status=400)
    try:
        attendance = get_object_or_404(Attendance, id=date)

        for student_dict in students:
            student = get_object_or_404(
                Student, admin_id=student_dict.get('id'))
            attendance_report = get_object_or_404(AttendanceReport, student=student, attendance=attendance)
            attendance_report.status = student_dict.get('status')
            attendance_report.save()
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'status': 'OK'})


def staff_apply_leave(request):
    form = LeaveReportStaffForm(request.POST or None)
    staff = get_object_or_404(Staff, admin_id=request.user.id)
    context = {
        'form': form,
        'leave_history': LeaveReportStaff.objects.filter(staff=staff),
        'page_title': 'Apply for Leave'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.staff = staff
                obj.save()
                messages.success(
                    request, "Application for leave has been submitted for review")
                return redirect(reverse('staff_apply_leave'))
            except Exception:
                messages.error(request, "Could not apply!")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "staff_template/staff_apply_leave.html", context)


def staff_feedback(request):
    form = FeedbackStaffForm(request.POST or None)
    staff = get_object_or_404(Staff, admin_id=request.user.id)
    context = {
        'form': form,
        'feedbacks': FeedbackStaff.objects.filter(staff=staff),
        'page_title': 'Add Feedback'
    }
    if request.method == 'POST':
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.staff = staff
                obj.save()
                messages.success(request, "Feedback submitted for review")
                return redirect(reverse('staff_feedback'))
            except Exception:
                messages.error(request, "Could not Submit!")
        else:
            messages.error(request, "Form has errors!")
    return render(request, "staff_template/staff_feedback.html", context)


def staff_view_profile(request):
    staff = get_object_or_404(Staff, admin=request.user)
    form = StaffEditForm(request.POST or None, request.FILES or None,instance=staff)
    context = {'form': form, 'page_title': 'View/Update Profile'}
    if request.method == 'POST':
        try:
            if form.is_valid():
                first_name = form.cleaned_data.get('first_name')
                last_name = form.cleaned_data.get('last_name')
                password = form.cleaned_data.get('password') or None
                address = form.cleaned_data.get('address')
                gender = form.cleaned_data.get('gender')
                passport = request.FILES.get('profile_pic') or None
                admin = staff.admin
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
                staff.save()
                messages.success(request, "Profile Updated!")
                return redirect(reverse('staff_view_profile'))
            else:
                messages.error(request, "Invalid Data Provided")
                return render(request, "staff_template/staff_view_profile.html", context)
        except Exception as e:
            messages.error(
                request, "Error Occured While Updating Profile " + str(e))
            return render(request, "staff_template/staff_view_profile.html", context)

    return render(request, "staff_template/staff_view_profile.html", context)


@csrf_exempt
def staff_fcmtoken(request):
    token = request.POST.get('token')
    try:
        staff_user = get_object_or_404(CustomUser, id=request.user.id)
        staff_user.fcm_token = token
        staff_user.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def staff_view_notification(request):
    staff = get_object_or_404(Staff, admin=request.user)
    notifications = NotificationStaff.objects.filter(staff=staff)
    context = {
        'notifications': notifications,
        'page_title': "View Notifications"
    }
    return render(request, "staff_template/staff_view_notification.html", context)


def staff_add_result(request):
    # MVP: Teachers can only enter results when admin opens result entry window
    from .result_entry_permissions import can_teacher_enter_legacy_results
    if not request.user.is_superuser and request.user.user_type != '1':
        session_id = request.POST.get('session') if request.method == 'POST' else None
        if not can_teacher_enter_legacy_results(request, session_id):
            return render(request, 'staff_template/result_entry_closed.html', {
                'page_title': 'Result Entry Closed',
                'message': 'Result upload is currently closed. Please contact the administrator.'
            }, status=403)
    # If user is superuser allow all subjects; otherwise limit to staff's subjects
    if request.user.is_superuser:
        subjects = Subject.objects.all()
    else:
        staff = get_object_or_404(Staff, admin=request.user)
        subjects = Subject.objects.filter(staff=staff)
    sessions = Session.objects.all()
    context = {
        'page_title': 'Result Upload',
        'subjects': subjects,
        'sessions': sessions
    }
    if request.method == 'POST':
        session_id = request.POST.get('session')
        if not request.user.is_superuser:
            try:
                sid = int(session_id) if session_id else None
            except (ValueError, TypeError):
                sid = None
            if not can_teacher_enter_legacy_results(request, sid):
                messages.error(request, "Result upload is closed for this session. Please contact the administrator.")
                return render(request, "staff_template/staff_add_result.html", context)
        try:
            student_id = request.POST.get('student_list')
            subject_id = request.POST.get('subject')
            test = request.POST.get('test')
            exam = request.POST.get('exam')
            student = get_object_or_404(Student, id=student_id)
            subject = get_object_or_404(Subject, id=subject_id)

            # Permission check: non-superuser staff must own the subject
            if not request.user.is_superuser:
                staff = get_object_or_404(Staff, admin=request.user)
                if subject.staff != staff:
                    messages.warning(request, "You don't have permission to add/update results for this subject")
                    return render(request, "staff_template/staff_add_result.html", context)

            try:
                data = StudentResult.objects.get(
                    student=student, subject=subject)
                data.exam = exam
                data.test = test
                data.save()
                messages.success(request, "Scores Updated")
            except StudentResult.DoesNotExist:
                result = StudentResult(student=student, subject=subject, test=test, exam=exam)
                result.save()
                messages.success(request, "Scores Saved")
        except Exception as e:
            messages.warning(request, "Error Occured While Processing Form")
    return render(request, "staff_template/staff_add_result.html", context)


@csrf_exempt
def fetch_student_result(request):
    from .result_entry_permissions import can_teacher_enter_legacy_results
    if not request.user.is_superuser and request.user.user_type != '1':
        if not can_teacher_enter_legacy_results(request):
            return JsonResponse({'error': 'Result upload is currently closed.'}, status=403)
    try:
        subject_id = request.POST.get('subject')
        student_id = request.POST.get('student')
        student = get_object_or_404(Student, id=student_id)
        subject = get_object_or_404(Subject, id=subject_id)

        # Permission check: non-superuser staff must own the subject
        if not request.user.is_superuser:
            staff = get_object_or_404(Staff, admin=request.user)
            if subject.staff != staff:
                return JsonResponse({'error': 'Unauthorized'}, status=403)

        result = StudentResult.objects.get(student=student, subject=subject)
        result_data = {
            'exam': result.exam,
            'test': result.test
        }
        return JsonResponse(result_data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Homework Management
def staff_add_homework(request):
    staff = get_object_or_404(Staff, admin=request.user)
    subjects = Subject.objects.filter(staff=staff)
    sessions = Session.objects.all()
    courses = Course.objects.filter(id__in=subjects.values_list('course_id', flat=True))
    
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'courses': courses,
        'page_title': 'Assign Homework'
    }
    
    if request.method == 'POST':
        subject_id = request.POST.get('subject')
        course_id = request.POST.get('course')
        session_id = request.POST.get('session')
        title = request.POST.get('title')
        description = request.POST.get('description')
        due_date = request.POST.get('due_date')
        max_marks = request.POST.get('max_marks', 100)
        attachment = request.FILES.get('attachment')
        
        try:
            subject = Subject.objects.get(id=subject_id)
            course = Course.objects.get(id=course_id)
            session = Session.objects.get(id=session_id)
            
            homework = Homework.objects.create(
                subject=subject,
                course=course,
                staff=staff,
                title=title,
                description=description,
                due_date=due_date,
                max_marks=max_marks,
                session=session,
                attachment=attachment
            )
            messages.success(request, "Homework assigned successfully!")
            return redirect(reverse('staff_manage_homework'))
        except Exception as e:
            messages.error(request, f"Error assigning homework: {str(e)}")
    
    return render(request, 'staff_template/staff_add_homework.html', context)


def staff_manage_homework(request):
    staff = get_object_or_404(Staff, admin=request.user)
    homework_list = Homework.objects.filter(staff=staff).select_related('subject', 'course')
    
    context = {
        'homework_list': homework_list,
        'page_title': 'Manage Homework'
    }
    return render(request, 'staff_template/staff_manage_homework.html', context)


def staff_edit_homework(request, homework_id):
    staff = get_object_or_404(Staff, admin=request.user)
    homework = get_object_or_404(Homework, id=homework_id, staff=staff)
    subjects = Subject.objects.filter(staff=staff)
    sessions = Session.objects.all()
    courses = Course.objects.filter(id__in=subjects.values_list('course_id', flat=True))
    
    if request.method == 'POST':
        homework.title = request.POST.get('title')
        homework.description = request.POST.get('description')
        homework.due_date = request.POST.get('due_date')
        homework.max_marks = request.POST.get('max_marks', 100)
        
        attachment = request.FILES.get('attachment')
        if attachment:
            homework.attachment = attachment
        
        try:
            homework.save()
            messages.success(request, "Homework updated successfully!")
            return redirect(reverse('staff_manage_homework'))
        except Exception as e:
            messages.error(request, f"Error updating homework: {str(e)}")
    
    context = {
        'homework': homework,
        'subjects': subjects,
        'sessions': sessions,
        'courses': courses,
        'page_title': 'Edit Homework'
    }
    return render(request, 'staff_template/staff_edit_homework.html', context)


def staff_delete_homework(request, homework_id):
    staff = get_object_or_404(Staff, admin=request.user)
    homework = get_object_or_404(Homework, id=homework_id, staff=staff)
    try:
        homework.delete()
        messages.success(request, "Homework deleted successfully!")
    except Exception as e:
        messages.error(request, f"Error deleting homework: {str(e)}")
    return redirect(reverse('staff_manage_homework'))


def staff_view_submissions(request, homework_id):
    staff = get_object_or_404(Staff, admin=request.user)
    homework = get_object_or_404(Homework, id=homework_id, staff=staff)
    submissions = HomeworkSubmission.objects.filter(homework=homework).select_related('student__admin')
    
    context = {
        'homework': homework,
        'submissions': submissions,
        'page_title': f'Submissions - {homework.title}'
    }
    return render(request, 'staff_template/staff_view_submissions.html', context)


def staff_grade_submission(request, submission_id):
    staff = get_object_or_404(Staff, admin=request.user)
    submission = get_object_or_404(HomeworkSubmission, id=submission_id, homework__staff=staff)
    
    if request.method == 'POST':
        marks = request.POST.get('marks')
        feedback = request.POST.get('feedback')
        
        try:
            from django.utils import timezone
            submission.marks_obtained = marks
            submission.feedback = feedback
            submission.graded_at = timezone.now()
            submission.save()
            messages.success(request, "Submission graded successfully!")
        except Exception as e:
            messages.error(request, f"Error grading submission: {str(e)}")
    
    return redirect(reverse('staff_view_submissions', args=[submission.homework.id]))


def staff_view_timetable(request):
    staff = get_object_or_404(Staff, admin=request.user)
    timetables = Timetable.objects.filter(staff=staff).select_related('course', 'subject').order_by('day', 'start_time')
    
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    timetable_by_day = {day: [] for day in days}
    for tt in timetables:
        if tt.day in timetable_by_day:
            timetable_by_day[tt.day].append(tt)
    
    context = {
        'timetable_by_day': timetable_by_day,
        'days': days,
        'page_title': 'My Timetable'
    }
    return render(request, 'staff_template/staff_view_timetable.html', context)


def staff_view_messages(request):
    messages_received = Message.objects.filter(recipient=request.user).order_by('-created_at')
    messages_sent = Message.objects.filter(sender=request.user).order_by('-created_at')
    
    context = {
        'messages_received': messages_received,
        'messages_sent': messages_sent,
        'page_title': 'Messages'
    }
    return render(request, 'staff_template/staff_view_messages.html', context)


def staff_send_message(request):
    staff = get_object_or_404(Staff, admin=request.user)
    
    # Get parents of students in staff's classes
    students = Student.objects.filter(course=staff.course)
    parents = Parent.objects.filter(children__in=students).distinct().select_related('admin')
    
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient_id')
        subject = request.POST.get('subject')
        content = request.POST.get('content')
        
        try:
            recipient = CustomUser.objects.get(id=recipient_id)
            Message.objects.create(
                sender=request.user,
                recipient=recipient,
                subject=subject,
                content=content
            )
            messages.success(request, "Message sent successfully!")
            return redirect(reverse('staff_view_messages'))
        except Exception as e:
            messages.error(request, f"Error sending message: {str(e)}")
    
    context = {
        'parents': parents,
        'page_title': 'Send Message'
    }
    return render(request, 'staff_template/staff_send_message.html', context)


def staff_reply_message(request, message_id):
    original_message = get_object_or_404(Message, id=message_id, recipient=request.user)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        
        try:
            Message.objects.create(
                sender=request.user,
                recipient=original_message.sender,
                subject=f"Re: {original_message.subject}",
                content=content,
                parent_message=original_message
            )
            original_message.is_read = True
            original_message.save()
            messages.success(request, "Reply sent successfully!")
        except Exception as e:
            messages.error(request, f"Error sending reply: {str(e)}")
    
    return redirect(reverse('staff_view_messages'))


# ============================================================
# CLASS MANAGEMENT FOR TEACHERS
# ============================================================

def staff_view_my_class(request):
    """View classes where staff is the class teacher"""
    staff = get_object_or_404(Staff, admin=request.user)
    
    # Get classes where this staff is the class teacher
    assigned_classes = Course.objects.filter(
        class_teacher=staff, 
        is_active=True
    ).select_related('grade_level', 'stream', 'academic_year')
    
    # Get classes where this staff teaches subjects
    teaching_classes = Course.objects.filter(
        subject__staff=staff
    ).distinct().select_related('grade_level', 'stream')
    
    context = {
        'assigned_classes': assigned_classes,
        'teaching_classes': teaching_classes,
        'page_title': 'My Classes'
    }
    return render(request, 'staff_template/staff_view_my_class.html', context)


def staff_view_class_roster(request, class_id):
    """View student roster for a class"""
    from .models import StudentClassEnrollment
    
    staff = get_object_or_404(Staff, admin=request.user)
    school_class = get_object_or_404(Course, id=class_id)
    
    # Verify staff has access to this class
    is_class_teacher = school_class.class_teacher == staff
    teaches_subject = Subject.objects.filter(staff=staff, course=school_class).exists()
    
    if not (is_class_teacher or teaches_subject):
        messages.error(request, "You don't have access to this class")
        return redirect(reverse('staff_view_my_class'))
    
    # Get enrolled students
    enrollments = StudentClassEnrollment.objects.filter(
        school_class=school_class,
        status='active'
    ).select_related('student__admin', 'academic_year')
    
    # Also get students directly assigned (backward compatibility)
    direct_students = Student.objects.filter(
        models.Q(course=school_class) | models.Q(current_class=school_class)
    ).select_related('admin')
    
    # Get subjects taught by this staff in this class
    subjects = Subject.objects.filter(staff=staff, course=school_class)
    
    context = {
        'school_class': school_class,
        'enrollments': enrollments,
        'direct_students': direct_students,
        'subjects': subjects,
        'is_class_teacher': is_class_teacher,
        'page_title': f'Class Roster - {school_class}'
    }
    return render(request, 'staff_template/staff_view_class_roster.html', context)

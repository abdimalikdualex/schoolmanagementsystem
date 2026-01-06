import json
import requests
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Q
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (HttpResponse, HttpResponseRedirect,
                              get_object_or_404, redirect, render)
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import UpdateView

from .forms import *
from .models import *


def admin_home(request):
    total_staff = Staff.objects.all().count()
    total_students = Student.objects.all().count()
    subjects = Subject.objects.all()
    total_subject = subjects.count()
    total_course = Course.objects.all().count()
    attendance_list = Attendance.objects.filter(subject__in=subjects)
    total_attendance = attendance_list.count()
    attendance_list = []
    subject_list = []
    for subject in subjects:
        attendance_count = Attendance.objects.filter(subject=subject).count()
        subject_list.append(subject.name[:7])
        attendance_list.append(attendance_count)

    # Total Subjects and students in Each Course
    course_all = Course.objects.all()
    course_name_list = []
    subject_count_list = []
    student_count_list_in_course = []

    for course in course_all:
        subjects = Subject.objects.filter(course_id=course.id).count()
        students = Student.objects.filter(course_id=course.id).count()
        course_name_list.append(course.name)
        subject_count_list.append(subjects)
        student_count_list_in_course.append(students)
    
    subject_all = Subject.objects.all()
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

    students = Student.objects.all()
    for student in students:
        
        attendance = AttendanceReport.objects.filter(student_id=student.id, status=True).count()
        absent = AttendanceReport.objects.filter(student_id=student.id, status=False).count()
        leave = LeaveReportStudent.objects.filter(student_id=student.id, status=1).count()
        student_attendance_present_list.append(attendance)
        student_attendance_leave_list.append(leave+absent)
        student_name_list.append(student.admin.first_name)

    context = {
        'page_title': "Administrative Dashboard",
        'total_students': total_students,
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
    form = StaffForm(request.POST or None, request.FILES or None)
    context = {'form': form, 'page_title': 'Add Staff'}
    if request.method == 'POST':
        if form.is_valid():
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            address = form.cleaned_data.get('address')
            email = form.cleaned_data.get('email')
            gender = form.cleaned_data.get('gender')
            password = form.cleaned_data.get('password')
            course = form.cleaned_data.get('course')
            passport = request.FILES.get('profile_pic')
            fs = FileSystemStorage()
            filename = fs.save(passport.name, passport)
            passport_url = fs.url(filename)
            try:
                user = CustomUser.objects.create_user(
                    email=email, password=password, user_type=2, first_name=first_name, last_name=last_name, profile_pic=passport_url)
                user.gender = gender
                user.address = address
                user.staff.course = course
                user.save()
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_staff'))

            except Exception as e:
                messages.error(request, "Could Not Add " + str(e))
        else:
            messages.error(request, "Please fulfil all requirements")

    return render(request, 'hod_template/add_staff_template.html', context)


def add_student(request):
    student_form = StudentForm(request.POST or None, request.FILES or None)
    context = {'form': student_form, 'page_title': 'Add Student'}
    if request.method == 'POST':
        if student_form.is_valid():
            first_name = student_form.cleaned_data.get('first_name')
            last_name = student_form.cleaned_data.get('last_name')
            address = student_form.cleaned_data.get('address')
            email = student_form.cleaned_data.get('email')
            gender = student_form.cleaned_data.get('gender')
            password = student_form.cleaned_data.get('password')
            course = student_form.cleaned_data.get('course')
            session = student_form.cleaned_data.get('session')
            passport = request.FILES['profile_pic']
            fs = FileSystemStorage()
            filename = fs.save(passport.name, passport)
            passport_url = fs.url(filename)
            try:
                user = CustomUser.objects.create_user(
                    email=email, password=password, user_type=3, first_name=first_name, last_name=last_name, profile_pic=passport_url)
                user.gender = gender
                user.address = address
                user.student.session = session
                user.student.course = course
                user.save()
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_student'))
            except Exception as e:
                messages.error(request, "Could Not Add: " + str(e))
        else:
            messages.error(request, "Could Not Add: ")
    return render(request, 'hod_template/add_student_template.html', context)


def add_course(request):
    form = CourseForm(request.POST or None)
    context = {
        'form': form,
        'page_title': 'Add Course'
    }
    if request.method == 'POST':
        if form.is_valid():
            name = form.cleaned_data.get('name')
            try:
                course = Course()
                course.name = name
                course.save()
                messages.success(request, "Successfully Added")
                return redirect(reverse('add_course'))
            except:
                messages.error(request, "Could Not Add")
        else:
            messages.error(request, "Could Not Add")
    return render(request, 'hod_template/add_course_template.html', context)


def add_subject(request):
    form = SubjectForm(request.POST or None)
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
    allStaff = CustomUser.objects.filter(user_type=2)
    context = {
        'allStaff': allStaff,
        'page_title': 'Manage Staff'
    }
    return render(request, "hod_template/manage_staff.html", context)


def manage_student(request):
    students = CustomUser.objects.filter(user_type=3)
    context = {
        'students': students,
        'page_title': 'Manage Students'
    }
    return render(request, "hod_template/manage_student.html", context)


def admission_setting_view(request):
    # Allow HOD and Staff to configure admission numbering
    if not request.user.is_authenticated or int(request.user.user_type) not in [1, 2]:
        return redirect('login_page')

    setting = AdmissionSetting.objects.first()
    if request.method == 'POST':
        prefix = request.POST.get('prefix', 'ADM').strip()
        start = request.POST.get('start_number')
        try:
            start = int(start)
        except Exception:
            start = None

        if not setting:
            setting = AdmissionSetting.objects.create(prefix=prefix, start_number=start or 1000, next_number=start or 1000, created_by=request.user)
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

    q = request.GET.get('q', '').strip()
    students = []
    if q:
        students = Student.objects.filter(models.Q(admission_number__iexact=q) |
                                          models.Q(admin__first_name__icontains=q) |
                                          models.Q(admin__last_name__icontains=q))

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

    student = get_object_or_404(Student, id=student_id)
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
    courses = Course.objects.all()
    context = {
        'courses': courses,
        'page_title': 'Manage Courses'
    }
    return render(request, "hod_template/manage_course.html", context)


def manage_subject(request):
    subjects = Subject.objects.all()
    context = {
        'subjects': subjects,
        'page_title': 'Manage Subjects'
    }
    return render(request, "hod_template/manage_subject.html", context)


def edit_staff(request, staff_id):
    staff = get_object_or_404(Staff, id=staff_id)
    form = StaffForm(request.POST or None, instance=staff)
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
        user = CustomUser.objects.get(id=staff_id)
        staff = Staff.objects.get(id=user.id)
        return render(request, "hod_template/edit_staff_template.html", context)


def edit_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    form = StudentForm(request.POST or None, instance=student)
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
    instance = get_object_or_404(Course, id=course_id)
    form = CourseForm(request.POST or None, instance=instance)
    context = {
        'form': form,
        'course_id': course_id,
        'page_title': 'Edit Course'
    }
    if request.method == 'POST':
        if form.is_valid():
            name = form.cleaned_data.get('name')
            try:
                course = Course.objects.get(id=course_id)
                course.name = name
                course.save()
                messages.success(request, "Successfully Updated")
            except:
                messages.error(request, "Could Not Update")
        else:
            messages.error(request, "Could Not Update")

    return render(request, 'hod_template/edit_course_template.html', context)


def edit_subject(request, subject_id):
    instance = get_object_or_404(Subject, id=subject_id)
    form = SubjectForm(request.POST or None, instance=instance)
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
                form.save()
                messages.success(request, "Session Created")
                return redirect(reverse('add_session'))
            except Exception as e:
                messages.error(request, 'Could Not Add ' + str(e))
        else:
            messages.error(request, 'Fill Form Properly ')
    return render(request, "hod_template/add_session_template.html", context)


def manage_session(request):
    sessions = Session.objects.all()
    context = {'sessions': sessions, 'page_title': 'Manage Sessions'}
    return render(request, "hod_template/manage_session.html", context)


def edit_session(request, session_id):
    instance = get_object_or_404(Session, id=session_id)
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


@csrf_exempt
def check_email_availability(request):
    email = request.POST.get("email")
    try:
        user = CustomUser.objects.filter(email=email).exists()
        if user:
            return HttpResponse(True)
        return HttpResponse(False)
    except Exception as e:
        return HttpResponse(False)


@csrf_exempt
def student_feedback_message(request):
    if request.method != 'POST':
        feedbacks = FeedbackStudent.objects.all()
        context = {
            'feedbacks': feedbacks,
            'page_title': 'Student Feedback Messages'
        }
        return render(request, 'hod_template/student_feedback_template.html', context)
    else:
        feedback_id = request.POST.get('id')
        try:
            feedback = get_object_or_404(FeedbackStudent, id=feedback_id)
            reply = request.POST.get('reply')
            feedback.reply = reply
            feedback.save()
            return HttpResponse(True)
        except Exception as e:
            return HttpResponse(False)


@csrf_exempt
def staff_feedback_message(request):
    if request.method != 'POST':
        feedbacks = FeedbackStaff.objects.all()
        context = {
            'feedbacks': feedbacks,
            'page_title': 'Staff Feedback Messages'
        }
        return render(request, 'hod_template/staff_feedback_template.html', context)
    else:
        feedback_id = request.POST.get('id')
        try:
            feedback = get_object_or_404(FeedbackStaff, id=feedback_id)
            reply = request.POST.get('reply')
            feedback.reply = reply
            feedback.save()
            return HttpResponse(True)
        except Exception as e:
            return HttpResponse(False)


@csrf_exempt
def view_staff_leave(request):
    if request.method != 'POST':
        allLeave = LeaveReportStaff.objects.all()
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
            leave = get_object_or_404(LeaveReportStaff, id=id)
            leave.status = status
            leave.save()
            return HttpResponse(True)
        except Exception as e:
            return False


@csrf_exempt
def view_student_leave(request):
    if request.method != 'POST':
        allLeave = LeaveReportStudent.objects.all()
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
            leave = get_object_or_404(LeaveReportStudent, id=id)
            leave.status = status
            leave.save()
            return HttpResponse(True)
        except Exception as e:
            return False


def admin_view_attendance(request):
    subjects = Subject.objects.all()
    sessions = Session.objects.all()
    context = {
        'subjects': subjects,
        'sessions': sessions,
        'page_title': 'View Attendance'
    }

    return render(request, "hod_template/admin_view_attendance.html", context)


@csrf_exempt
def get_admin_attendance(request):
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    attendance_date_id = request.POST.get('attendance_date_id')
    try:
        subject = get_object_or_404(Subject, id=subject_id)
        session = get_object_or_404(Session, id=session_id)
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
        return JsonResponse(json.dumps(json_data), safe=False)
    except Exception as e:
        return None


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
    staff = CustomUser.objects.filter(user_type=2)
    context = {
        'page_title': "Send Notifications To Staff",
        'allStaff': staff
    }
    return render(request, "hod_template/staff_notification.html", context)


def admin_notify_student(request):
    student = CustomUser.objects.filter(user_type=3)
    context = {
        'page_title': "Send Notifications To Students",
        'students': student
    }
    return render(request, "hod_template/student_notification.html", context)


@csrf_exempt
def send_student_notification(request):
    id = request.POST.get('id')
    message = request.POST.get('message')
    student = get_object_or_404(Student, admin_id=id)
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
        return HttpResponse("True")
    except Exception as e:
        return HttpResponse("False")


@csrf_exempt
def send_staff_notification(request):
    id = request.POST.get('id')
    message = request.POST.get('message')
    staff = get_object_or_404(Staff, admin_id=id)
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
        return HttpResponse("True")
    except Exception as e:
        return HttpResponse("False")


def delete_staff(request, staff_id):
    staff = get_object_or_404(CustomUser, staff__id=staff_id)
    staff.delete()
    messages.success(request, "Staff deleted successfully!")
    return redirect(reverse('manage_staff'))


def delete_student(request, student_id):
    student = get_object_or_404(CustomUser, student__id=student_id)
    student.delete()
    messages.success(request, "Student deleted successfully!")
    return redirect(reverse('manage_student'))


def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    try:
        course.delete()
        messages.success(request, "Course deleted successfully!")
    except Exception:
        messages.error(
            request, "Sorry, some students are assigned to this course already. Kindly change the affected student course and try again")
    return redirect(reverse('manage_course'))


def delete_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    subject.delete()
    messages.success(request, "Subject deleted successfully!")
    return redirect(reverse('manage_subject'))


def delete_session(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    try:
        session.delete()
        messages.success(request, "Session deleted successfully!")
    except Exception:
        messages.error(
            request, "There are students assigned to this session. Please move them to another session.")
    return redirect(reverse('manage_session'))


def admin_view_result(request):
    """Admin can view all student results"""
    courses = Course.objects.all()
    subjects = Subject.objects.all()
    context = {
        'page_title': 'View Student Results',
        'courses': courses,
        'subjects': subjects
    }
    return render(request, 'hod_template/admin_view_result.html', context)


@csrf_exempt
def admin_get_students_for_result(request):
    """Fetch students by course and subject for admin"""
    try:
        course_id = request.POST.get('course_id')
        subject_id = request.POST.get('subject_id')
        
        if course_id and subject_id:
            students = Student.objects.filter(course_id=course_id)
            subject = get_object_or_404(Subject, id=subject_id)
            
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
            
            return JsonResponse(json.dumps(student_result_data), content_type='application/json', safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def admin_edit_result(request):
    """Only superuser and staff can edit student results"""
    # Restrict to superuser only - regular admins cannot edit results
    if not request.user.is_superuser:
        messages.error(request, "Only super admin and staff can edit student results")
        return redirect('admin_home')
    
    subjects = Subject.objects.all()
    courses = Course.objects.all()
    students = Student.objects.all()
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
            
            student = get_object_or_404(Student, id=student_id)
            subject = get_object_or_404(Subject, id=subject_id)
            
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
    """Fetch specific student result for admin"""
    try:
        subject_id = request.POST.get('subject_id')
        student_id = request.POST.get('student_id')
        
        student = get_object_or_404(Student, id=student_id)
        subject = get_object_or_404(Subject, id=subject_id)
        
        result = StudentResult.objects.get(student=student, subject=subject)
        result_data = {
            'exam': result.exam,
            'test': result.test,
            'student_name': student.admin.last_name + " " + student.admin.first_name
        }
        return HttpResponse(json.dumps(result_data))
    except StudentResult.DoesNotExist:
        return HttpResponse(json.dumps({
            'exam': 0,
            'test': 0,
            'student_name': student.admin.last_name + " " + student.admin.first_name
        }))
    except Exception as e:
        return HttpResponse('False')


def admin_view_transcript(request):
    """View student transcripts for printing"""
    students = Student.objects.all()
    context = {
        'students': students,
        'page_title': 'Student Transcripts'
    }
    return render(request, 'hod_template/admin_view_transcript.html', context)


def admin_get_student_transcript(request):
    """Get detailed transcript for a specific student"""
    try:
        student_id = request.POST.get('student_id')
        student = get_object_or_404(Student, id=student_id)
        
        results = StudentResult.objects.filter(student=student)
        
        transcript_data = {
            'student_name': student.admin.last_name + " " + student.admin.first_name,
            'student_id': student.admin.username,
            'course': student.course.name,
            'session': student.session.session if student.session else 'N/A',
            'results': []
        }
        
        total_marks = 0
        total_subjects = 0
        
        for result in results:
            total = result.test + result.exam
            total_marks += total
            total_subjects += 1
            
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
            
            transcript_data['results'].append({
                'subject': result.subject.name,
                'test': result.test,
                'exam': result.exam,
                'total': total,
                'grade': grade
            })
        
        # Calculate GPA (average)
        if total_subjects > 0:
            transcript_data['average'] = round(total_marks / total_subjects, 2)
        else:
            transcript_data['average'] = 0
        
        return HttpResponse(json.dumps(transcript_data))
    except Exception as e:
        return HttpResponse(json.dumps({'error': str(e)}))


def admin_view_fees(request):
    """View and manage student fees"""
    if not request.user.is_superuser:
        # Check if admin has permission to view fees
        try:
            perm = AdminPermission.objects.get(admin=request.user)
            if not perm.can_view_fees:
                messages.error(request, "You don't have permission to view fees")
                return redirect('admin_home')
        except AdminPermission.DoesNotExist:
            messages.error(request, "You don't have permission to view fees")
            return redirect('admin_home')
    
    students = Student.objects.all()
    sessions = Session.objects.all()
    context = {
        'students': students,
        'sessions': sessions,
        'page_title': 'Student Fees Management'
    }
    return render(request, 'hod_template/admin_view_fees.html', context)


def admin_post_fees(request):
    """Post/Create fees for students"""
    if not request.user.is_superuser:
        try:
            perm = AdminPermission.objects.get(admin=request.user)
            if not perm.can_manage_fees:
                return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
        except AdminPermission.DoesNotExist:
            return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
    
    if request.method == 'POST':
        try:
            student_id = request.POST.get('student_id')
            session_id = request.POST.get('session_id')
            amount = float(request.POST.get('amount'))
            due_date = request.POST.get('due_date')
            notes = request.POST.get('notes', '')
            
            student = get_object_or_404(Student, id=student_id)
            session = get_object_or_404(Session, id=session_id)
            
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
    """Fetch fees for a student via AJAX"""
    try:
        student_id = request.POST.get('student_id')
        session_id = request.POST.get('session_id')
        
        student = get_object_or_404(Student, id=student_id)
        session = get_object_or_404(Session, id=session_id)
        
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
            return HttpResponse(json.dumps(fees_data))
        except StudentFees.DoesNotExist:
            return HttpResponse(json.dumps({'message': 'No fees found'}))
    except Exception as e:
        return HttpResponse(json.dumps({'error': str(e)}))


def admin_clear_fees(request):
    """Clear/Update fees payment"""
    if not request.user.is_superuser:
        try:
            perm = AdminPermission.objects.get(admin=request.user)
            if not perm.can_manage_fees:
                return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
        except AdminPermission.DoesNotExist:
            return JsonResponse({'error': 'You do not have permission to manage fees'}, status=403)
    
    if request.method == 'POST':
        try:
            fees_id = request.POST.get('fees_id')
            amount_paid = Decimal(request.POST.get('amount_paid'))
            payment_date = request.POST.get('payment_date', datetime.now().date())
            
            fees = get_object_or_404(StudentFees, id=fees_id)
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
    """Super admin manage permissions for other admins"""
    if not request.user.is_superuser:
        messages.error(request, "Only super admin can manage permissions")
        return redirect('admin_home')
    
    admins = CustomUser.objects.filter(user_type=1).exclude(is_superuser=True)
    context = {
        'admins': admins,
        'page_title': 'Manage Admin Permissions'
    }
    return render(request, 'hod_template/admin_manage_permissions.html', context)


def admin_update_permission(request):
    """Update admin permissions"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            admin_id = request.POST.get('admin_id')
            permission_type = request.POST.get('permission_type')
            value = request.POST.get('value').lower() == 'true'
            
            admin_user = get_object_or_404(CustomUser, id=admin_id)
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


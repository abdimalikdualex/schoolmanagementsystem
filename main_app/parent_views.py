import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    Parent, Student, CustomUser, Attendance, AttendanceReport,
    StudentResult, StudentFees, Homework, HomeworkSubmission,
    Announcement, Message, NotificationParent, Timetable, Session,
    FeePayment, StudentExamResult, ClassAttendanceRecord, Guardian,
    AcademicTerm,
)


def parent_home(request):
    parent = get_object_or_404(Parent, admin=request.user)
    children = parent.children.all().select_related('admin', 'course', 'current_class')
    
    total_children = children.count()
    active_term = AcademicTerm.get_active_term()
    
    # Get announcements for parents
    announcements = Announcement.objects.filter(
        Q(target_audience='all') | Q(target_audience='parents'),
        is_active=True
    ).order_by('-publish_date')[:5]
    
    # Get unread messages count
    unread_messages = Message.objects.filter(recipient=request.user, is_read=False).count()
    
    # Get notifications
    notifications = NotificationParent.objects.filter(parent=parent, is_read=False).count()
    
    # Children summary data with attendance, latest grade
    children_data = []
    overall_attendance_pct = 0
    latest_grade = None
    for child in children:
        # Get attendance data - try new ClassAttendanceRecord first, then legacy
        total_attendance = ClassAttendanceRecord.objects.filter(student=child).count()
        if total_attendance > 0:
            present = ClassAttendanceRecord.objects.filter(student=child, status='present').count()
        else:
            # Fallback to legacy attendance
            total_attendance = AttendanceReport.objects.filter(student=child).count()
            present = AttendanceReport.objects.filter(student=child, status=True).count()
        attendance_percentage = round((present / total_attendance) * 100, 1) if total_attendance > 0 else 0
        
        # Get fees data - try new FeePayment first, then legacy
        total_paid = FeePayment.objects.filter(student=child, is_reversed=False).aggregate(
            total=Sum('amount'))['total'] or 0
        total_billed = child.total_fee_billed or 0
        
        if total_billed > 0:
            if total_paid >= total_billed:
                fees_status = 'Paid'
            elif total_paid > 0:
                fees_status = 'Partial'
            else:
                fees_status = 'Unpaid'
        else:
            # Fallback to legacy fees
            fees = StudentFees.objects.filter(student=child).order_by('-created_at').first()
            fees_status = fees.status if fees else 'N/A'
        
        # Get recent results - try new StudentExamResult first, then legacy
        exam_results_qs = StudentExamResult.objects.filter(student=child).select_related('subject', 'academic_year')
        results_count = exam_results_qs.count()
        if results_count == 0:
            results_count = StudentResult.objects.filter(student=child).count()
        
        # Latest grade from most recent exam result
        last_result = exam_results_qs.order_by('-academic_year__start_year', '-term').first()
        child_grade = last_result.grade if last_result and last_result.grade else None
        if child_grade and not latest_grade:
            latest_grade = child_grade
        
        # Average for display (latest term if available)
        child_avg = None
        if last_result:
            term_results = exam_results_qs.filter(
                academic_year=last_result.academic_year, term=last_result.term
            )
            total_scr = sum(r.score for r in term_results)
            total_out = sum(r.out_of for r in term_results)
            child_avg = round((total_scr / total_out) * 100, 1) if total_out else None
        
        children_data.append({
            'student': child,
            'attendance_percentage': attendance_percentage,
            'fees_status': fees_status,
            'results_count': results_count,
            'latest_grade': child_grade,
            'average': child_avg,
        })
    
    # Overall attendance (average across children)
    if children_data:
        overall_attendance_pct = round(sum(c['attendance_percentage'] for c in children_data) / len(children_data), 1)
    
    context = {
        'page_title': 'Parent Dashboard',
        'parent': parent,
        'children': children,
        'children_data': children_data,
        'total_children': total_children,
        'active_term': active_term,
        'overall_attendance_pct': overall_attendance_pct,
        'latest_grade': latest_grade or 'N/A',
        'announcements': announcements,
        'unread_messages': unread_messages,
        'notifications': notifications,
    }
    return render(request, 'parent_template/home_content.html', context)


def parent_view_children(request):
    parent = get_object_or_404(Parent, admin=request.user)
    children = parent.children.all().select_related('admin', 'course', 'session', 'current_class')
    
    context = {
        'page_title': 'My Children',
        'children': children,
    }
    return render(request, 'parent_template/view_children.html', context)


def parent_view_attendance(request):
    """Attendance hub - redirect to child if one, else show child selector"""
    parent = get_object_or_404(Parent, admin=request.user)
    children = parent.children.all().select_related('admin', 'course', 'current_class')
    if children.count() == 1:
        return redirect('parent_view_child_attendance', student_id=children.first().id)
    context = {'page_title': 'Attendance', 'children': children}
    return render(request, 'parent_template/view_attendance_selector.html', context)


def parent_view_results(request):
    """Results hub - redirect to child if one, else show child selector"""
    parent = get_object_or_404(Parent, admin=request.user)
    children = parent.children.all().select_related('admin', 'course', 'current_class')
    if children.count() == 1:
        return redirect('parent_view_child_results', student_id=children.first().id)
    context = {'page_title': 'Results', 'children': children}
    return render(request, 'parent_template/view_results_selector.html', context)


def parent_view_child_profile(request, student_id):
    """Child profile page with tabs: Overview, Attendance, Subjects, Results, Report Cards"""
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    if student not in parent.children.all():
        messages.error(request, "You don't have access to this student")
        return redirect('parent_view_children')
    context = {
        'page_title': f"{student.admin.first_name} {student.admin.last_name}",
        'student': student,
    }
    return render(request, 'parent_template/view_child_profile.html', context)


def parent_view_report_card(request, student_id):
    """View report card for a child - per term"""
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    if student not in parent.children.all():
        messages.error(request, "You don't have access to this student")
        return redirect('parent_view_children')
    # Get available terms with results
    exam_results = StudentExamResult.objects.filter(student=student).values_list(
        'academic_year_id', 'term'
    ).distinct().order_by('-academic_year_id', 'term')
    terms_data = []
    for ay_id, term in exam_results:
        ay = Session.objects.filter(id=ay_id).first()
        if ay:
            terms_data.append({'academic_year': ay, 'term': term})
    context = {
        'page_title': f"Report Card - {student.admin.first_name}",
        'student': student,
        'terms_data': terms_data,
    }
    return render(request, 'parent_template/view_report_card.html', context)


def parent_download_report_card_pdf(request, student_id):
    """Download report card PDF for parent's child"""
    from django.conf import settings
    from django.core.files.storage import FileSystemStorage
    import os
    from datetime import datetime
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    if student not in parent.children.all():
        messages.error(request, "You don't have access to this student")
        return redirect('parent_view_children')
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
    except ImportError:
        messages.error(request, "PDF generation is not available.")
        return redirect('parent_view_report_card', student_id=student_id)
    term_filter = request.GET.get('term', '')
    year_filter = request.GET.get('year', '')
    results = StudentExamResult.objects.filter(student=student).select_related(
        'subject', 'exam_type', 'academic_year'
    ).order_by('academic_year__start_year', 'term', 'subject__name')
    if year_filter:
        results = results.filter(academic_year_id=int(year_filter))
    if term_filter:
        results = results.filter(term=term_filter)
    response = HttpResponse(content_type='application/pdf')
    filename = f"ReportCard_{student.admission_number or student.id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    doc = SimpleDocTemplate(response, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    title = Paragraph(
        f"<b>REPORT CARD - {student.admin.first_name} {student.admin.last_name}</b>",
        ParagraphStyle('Title', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER)
    )
    story.append(title)
    story.append(Spacer(1, 0.2 * inch))
    table_data = [['Subject', 'Score', 'Out Of', 'Grade']]
    for r in results:
        table_data.append([r.subject.name, str(r.score), str(r.out_of), r.grade or '-'])
    if len(table_data) > 1:
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(t)
    doc.build(story)
    return response


def parent_view_child_attendance(request, student_id):
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    
    if student not in parent.children.all():
        messages.error(request, "You don't have permission to view this student's attendance")
        return redirect('parent_home')
    
    term_filter = request.GET.get('term', '')
    
    # Try ClassAttendanceRecord first (new system)
    class_records = ClassAttendanceRecord.objects.filter(
        student=student
    ).select_related('class_attendance__session', 'class_attendance__term').order_by('-class_attendance__date')
    
    if term_filter:
        try:
            class_records = class_records.filter(class_attendance__term_id=int(term_filter))
        except ValueError:
            pass
    
    if class_records.exists():
        total = class_records.count()
        present = class_records.filter(status='present').count()
        absent = total - present
        percentage = round((present / total) * 100, 1) if total > 0 else 0
        attendance_records = [
            {
                'date': r.class_attendance.date,
                'subject': None,
                'session': r.class_attendance.session,
                'status': r.status == 'present',
                'status_label': r.get_status_display(),
            }
            for r in class_records
        ]
        use_class_attendance = True
    else:
        # Fallback to legacy AttendanceReport
        attendance_reports = AttendanceReport.objects.filter(student=student).select_related(
            'attendance__subject', 'attendance__session'
        ).order_by('-attendance__date')
        total = attendance_reports.count()
        present = attendance_reports.filter(status=True).count()
        absent = total - present
        percentage = round((present / total) * 100, 1) if total > 0 else 0
        attendance_records = [
            {
                'date': r.attendance.date,
                'subject': r.attendance.subject,
                'session': r.attendance.session,
                'status': r.status,
                'status_label': 'Present' if r.status else 'Absent',
            }
            for r in attendance_reports
        ]
        use_class_attendance = False
    
    # Get terms for filter
    terms = AcademicTerm.objects.all().order_by('-academic_year', 'term_name')[:10]
    
    context = {
        'page_title': f"Attendance - {student.admin.first_name}",
        'student': student,
        'attendance_records': attendance_records,
        'total': total,
        'present': present,
        'absent': absent,
        'percentage': percentage,
        'term_filter': term_filter,
        'terms': terms,
        'use_class_attendance': use_class_attendance,
    }
    return render(request, 'parent_template/view_attendance.html', context)


def parent_view_child_results(request, student_id):
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    
    # Verify this student belongs to this parent
    if student not in parent.children.all():
        messages.error(request, "You don't have permission to view this student's results")
        return redirect('parent_home')
    
    # Try new StudentExamResult first
    new_results = StudentExamResult.objects.filter(student=student).select_related(
        'subject', 'exam_type', 'academic_year'
    ).order_by('-academic_year__start_year', 'term', 'subject__name')
    
    if new_results.exists():
        # Use new exam system
        total_marks = sum(r.score for r in new_results)
        total_possible = sum(r.out_of for r in new_results)
        total_subjects = new_results.count()
        average = round((total_marks / total_possible) * 100, 2) if total_possible > 0 else 0
        
        context = {
            'page_title': f"Results - {student.admin.first_name}",
            'student': student,
            'new_results': new_results,
            'results': None,
            'total_marks': total_marks,
            'total_possible': total_possible,
            'average': average,
            'use_new_system': True,
        }
    else:
        # Fallback to legacy StudentResult
        results = StudentResult.objects.filter(student=student).select_related('subject')
        
        total_marks = 0
        total_subjects = 0
        for result in results:
            total_marks += result.test + result.exam
            total_subjects += 1
        
        average = round(total_marks / total_subjects, 2) if total_subjects > 0 else 0
        
        context = {
            'page_title': f"Results - {student.admin.first_name}",
            'student': student,
            'results': results,
            'new_results': None,
            'total_marks': total_marks,
            'average': average,
            'use_new_system': False,
        }
    
    return render(request, 'parent_template/view_results.html', context)


def parent_view_child_fees(request, student_id):
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    
    # Verify this student belongs to this parent
    if student not in parent.children.all():
        messages.error(request, "You don't have permission to view this student's fees")
        return redirect('parent_home')
    
    # Try new FeePayment model first
    payments = FeePayment.objects.filter(student=student, is_reversed=False).order_by('-payment_date')
    
    if payments.exists():
        # Use new fee system
        total_paid = payments.aggregate(total=Sum('amount'))['total'] or 0
        total_due = student.total_fee_billed or 0
        total_outstanding = total_due - total_paid
        
        context = {
            'page_title': f"Fees - {student.admin.first_name}",
            'student': student,
            'payments': payments,
            'fees': None,  # No legacy fees
            'total_due': total_due,
            'total_paid': total_paid,
            'total_outstanding': total_outstanding,
            'use_new_system': True,
        }
    else:
        # Fallback to legacy StudentFees
        fees = StudentFees.objects.filter(student=student).select_related('session').order_by('-created_at')
        
        total_due = sum(f.amount_due for f in fees)
        total_paid = sum(f.amount_paid for f in fees)
        total_outstanding = total_due - total_paid
        
        context = {
            'page_title': f"Fees - {student.admin.first_name}",
            'student': student,
            'fees': fees,
            'payments': None,
            'total_due': total_due,
            'total_paid': total_paid,
            'total_outstanding': total_outstanding,
            'use_new_system': False,
        }
    
    return render(request, 'parent_template/view_fees.html', context)


def parent_view_child_timetable(request, student_id):
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    
    # Verify this student belongs to this parent
    if student not in parent.children.all():
        messages.error(request, "You don't have permission to view this student's timetable")
        return redirect('parent_home')
    
    timetables = Timetable.objects.filter(
        course=student.course
    ).select_related('subject', 'staff__admin').order_by('day', 'start_time')
    
    # Organize by day
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    timetable_by_day = {day: [] for day in days}
    for tt in timetables:
        if tt.day in timetable_by_day:
            timetable_by_day[tt.day].append(tt)
    
    context = {
        'page_title': f"Timetable - {student.admin.first_name}",
        'student': student,
        'timetable_by_day': timetable_by_day,
        'days': days,
    }
    return render(request, 'parent_template/view_timetable.html', context)


def parent_view_child_homework(request, student_id):
    parent = get_object_or_404(Parent, admin=request.user)
    student = get_object_or_404(Student, id=student_id)
    
    # Verify this student belongs to this parent
    if student not in parent.children.all():
        messages.error(request, "You don't have permission to view this student's homework")
        return redirect('parent_home')
    
    homework_list = Homework.objects.filter(course=student.course).select_related(
        'subject', 'staff__admin'
    ).order_by('-due_date')
    
    # Get submission status for each homework
    homework_data = []
    for hw in homework_list:
        submission = HomeworkSubmission.objects.filter(homework=hw, student=student).first()
        homework_data.append({
            'homework': hw,
            'submission': submission,
            'status': 'Submitted' if submission else 'Pending'
        })
    
    context = {
        'page_title': f"Homework - {student.admin.first_name}",
        'student': student,
        'homework_data': homework_data,
    }
    return render(request, 'parent_template/view_homework.html', context)


def parent_view_announcements(request):
    parent = get_object_or_404(Parent, admin=request.user)
    children = parent.children.all()
    
    # Get course IDs for children
    course_ids = [child.course_id for child in children if child.course]
    
    announcements = Announcement.objects.filter(
        Q(target_audience='all') | 
        Q(target_audience='parents') |
        Q(target_audience='class', target_course_id__in=course_ids),
        is_active=True
    ).order_by('-publish_date')
    
    context = {
        'page_title': 'Announcements',
        'announcements': announcements,
    }
    return render(request, 'parent_template/view_announcements.html', context)


def parent_view_messages(request):
    messages_received = Message.objects.filter(recipient=request.user).order_by('-created_at')
    messages_sent = Message.objects.filter(sender=request.user).order_by('-created_at')
    
    context = {
        'page_title': 'Messages',
        'messages_received': messages_received,
        'messages_sent': messages_sent,
    }
    return render(request, 'parent_template/view_messages.html', context)


def parent_send_message(request):
    parent = get_object_or_404(Parent, admin=request.user)
    children = parent.children.all()
    
    # Get teachers who teach the parent's children
    teachers = set()
    for child in children:
        if child.course:
            from .models import Subject
            subjects = Subject.objects.filter(course=child.course).select_related('staff__admin')
            for subject in subjects:
                teachers.add(subject.staff)
    
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
            return redirect('parent_view_messages')
        except Exception as e:
            messages.error(request, f"Error sending message: {str(e)}")
    
    context = {
        'page_title': 'Send Message',
        'teachers': list(teachers),
    }
    return render(request, 'parent_template/send_message.html', context)


@csrf_exempt
def parent_mark_message_read(request):
    if request.method == 'POST':
        message_id = request.POST.get('message_id')
        try:
            msg = Message.objects.get(id=message_id, recipient=request.user)
            msg.is_read = True
            msg.save()
            return JsonResponse({'success': True})
        except:
            return JsonResponse({'success': False})
    return JsonResponse({'success': False})


def parent_view_profile(request):
    from django.contrib.auth import update_session_auth_hash
    
    parent = get_object_or_404(Parent, admin=request.user)
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone_number')
        address = request.POST.get('address')
        email = request.POST.get('email')
        password = request.POST.get('password')
        profile_pic = request.FILES.get('profile_pic')
        
        try:
            user = request.user
            user.first_name = first_name
            user.last_name = last_name
            user.phone_number = phone or None
            user.address = address or ''
            if email and email != user.email:
                if CustomUser.objects.exclude(pk=user.pk).filter(email=email).exists():
                    messages.error(request, "Email already in use by another account.")
                else:
                    user.email = email
            if password:
                user.set_password(password)
                update_session_auth_hash(request, user)
            if profile_pic:
                user.profile_pic = profile_pic
            user.save()
            messages.success(request, "Profile updated successfully!")
        except Exception as e:
            messages.error(request, f"Error updating profile: {str(e)}")
    
    context = {
        'page_title': 'My Profile',
        'parent': parent,
    }
    return render(request, 'parent_template/view_profile.html', context)


def parent_view_notifications(request):
    parent = get_object_or_404(Parent, admin=request.user)
    notifications = NotificationParent.objects.filter(parent=parent).order_by('-created_at')
    
    # Mark all as read
    notifications.update(is_read=True)
    
    context = {
        'page_title': 'Notifications',
        'notifications': notifications,
    }
    return render(request, 'parent_template/view_notifications.html', context)


@csrf_exempt
def parent_fcmtoken(request):
    token = request.POST.get('token')
    try:
        request.user.fcm_token = token
        request.user.save()
        return HttpResponse("True")
    except Exception as e:
        return HttpResponse("False")


# ============================================================
# CLASS INFO FOR PARENTS
# ============================================================

def parent_view_child_class(request, student_id):
    """Parent view child's class information"""
    from .models import StudentClassEnrollment
    
    parent = get_object_or_404(Parent, admin=request.user)
    
    # Verify this is parent's child
    student = get_object_or_404(Student, id=student_id)
    if student not in parent.children.all():
        messages.error(request, "You don't have access to this student's information")
        return redirect(reverse('parent_view_children'))
    
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
        'page_title': f"{student}'s Class"
    }
    return render(request, 'parent_template/view_child_class.html', context)

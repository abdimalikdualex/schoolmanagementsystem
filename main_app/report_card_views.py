"""
Kenyan KNEC-based Report Card views.
Supports Opener, Midterm, End-Term exams with automatic grade calculation.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db.models import Q, Sum, Count
from django.utils import timezone

from .models import (
    KNECReportCardResult, Student, Subject, Course, AcademicTerm, Session,
    ClassAttendance, ClassAttendanceRecord, StudentClassEnrollment,
    SchoolSettings, School
)
from .knec_utils import get_knec_grade, get_mean_grade_from_points
from .sms_service import get_school_settings

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _get_school_from_request(request):
    return getattr(request, 'school', None)


def _filter_by_school(qs, school, model_name=''):
    """Filter queryset by school for multi-tenant isolation."""
    if not school:
        return qs.none()
    if hasattr(qs.model, 'school'):
        return qs.filter(school=school)
    if hasattr(qs.model, 'admin') and hasattr(qs.model.admin.field.related_model, 'school'):
        return qs.filter(admin__school=school)
    if model_name == 'Student':
        return qs.filter(admin__school=school)
    if model_name == 'Subject' or (hasattr(qs.model, 'course')):
        return qs.filter(course__school=school)
    if hasattr(qs.model, 'academic_term') and hasattr(AcademicTerm, 'school'):
        return qs.filter(academic_term__school=school)
    return qs


def report_card_list(request):
    """List report cards - select class and term, then show students."""
    school = _get_school_from_request(request)
    if not school:
        messages.warning(request, "School context required.")
        return redirect('admin_home')

    academic_terms = AcademicTerm.objects.filter(school=school).order_by('-academic_year', 'term_name')
    courses = Course.objects.filter(school=school, is_active=True).order_by('name')

    term_id = request.GET.get('term')
    class_id = request.GET.get('course') or request.GET.get('class')

    students = []
    selected_term = None
    selected_class = None

    if term_id and class_id:
        selected_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
        selected_class = get_object_or_404(Course, id=class_id, school=school)
        enrollments = StudentClassEnrollment.objects.filter(
            school_class=selected_class,
            status='active',
            student__admin__school=school
        ).select_related('student__admin')
        if selected_term:
            enrollments = enrollments.filter(
                Q(term=selected_term) | Q(academic_year__academic_year=selected_term.academic_year)
            )
        for enr in enrollments:
            results = KNECReportCardResult.objects.filter(
                student=enr.student, academic_term=selected_term
            ).count()
            students.append({
                'enrollment': enr,
                'student': enr.student,
                'has_results': results > 0,
                'result_count': results,
            })

    context = {
        'page_title': 'Report Cards',
        'academic_terms': academic_terms,
        'courses': courses,
        'students': students,
        'selected_term': selected_term,
        'selected_class': selected_class,
        'term_id': term_id,
        'class_id': class_id,
    }
    return render(request, 'hod_template/report_card_list.html', context)


def _build_report_card_context(student, academic_term, school):
    """Build context for a single student's report card."""
    settings_obj = get_school_settings(school)
    school_obj = school

    results = KNECReportCardResult.objects.filter(
        student=student, academic_term=academic_term
    ).select_related('subject').order_by('subject__name')

    total_points = sum(r.points for r in results)
    total_subjects = results.count()
    mean_score = (sum(r.average for r in results) / total_subjects) if total_subjects else 0
    mean_grade = get_mean_grade_from_points(total_points / total_subjects) if total_subjects else 'E'

    # Position in class
    school_class = student.get_class_info() or student.current_class
    all_student_totals = []
    enrollments = []
    if school_class:
        enrollments = list(StudentClassEnrollment.objects.filter(
            school_class=school_class,
            status='active'
        ).filter(
            Q(term=academic_term) | Q(academic_year__academic_year=academic_term.academic_year)
        ).select_related('student'))
        for enr in enrollments:
            pts = KNECReportCardResult.objects.filter(
                student=enr.student, academic_term=academic_term
            ).aggregate(t=Sum('points'))['t'] or 0
            all_student_totals.append((enr.student.id, pts))
    all_student_totals.sort(key=lambda x: x[1], reverse=True)
    position = next((i + 1 for i, (sid, _) in enumerate(all_student_totals) if sid == student.id), None)

    # Attendance
    days_open = 0
    days_present = 0
    days_absent = 0
    if school_class:
        term_start = academic_term.start_date
        term_end = academic_term.end_date
        attendances = ClassAttendance.objects.filter(
            school_class=school_class,
            term=academic_term,
            date__gte=term_start,
            date__lte=term_end
        )
        days_open = attendances.count()
        for att in attendances:
            rec = ClassAttendanceRecord.objects.filter(
                class_attendance=att, student=student
            ).first()
            if rec:
                if rec.status == 'present':
                    days_present += 1
                elif rec.status == 'absent':
                    days_absent += 1

    # Next term opening - try to get next term's start_date
    next_terms = AcademicTerm.objects.filter(
        school=school,
        academic_year__gte=academic_term.academic_year
    ).exclude(id=academic_term.id).order_by('academic_year', 'term_name')
    next_term_opening = next_terms.first().start_date if next_terms.exists() else None

    school_class = student.get_class_info() or student.current_class
    return {
        'student': student,
        'school_class': school_class,
        'academic_term': academic_term,
        'results': results,
        'total_points': total_points,
        'total_subjects': total_subjects,
        'mean_score': round(mean_score, 2),
        'mean_grade': mean_grade,
        'position_in_class': position,
        'days_open': days_open,
        'days_present': days_present,
        'days_absent': days_absent,
        'next_term_opening': next_term_opening,
        'school': school_obj,
        'settings': settings_obj,
        'class_teacher_comment': '',
        'head_teacher_comment': '',
        'student_conduct': '',
    }


def report_card_view(request, student_id, term_id):
    """View single student report card (print-ready)."""
    school = _get_school_from_request(request)
    if not school:
        messages.warning(request, "School context required.")
        return redirect('admin_home')

    student = get_object_or_404(Student, id=student_id, admin__school=school)
    academic_term = get_object_or_404(AcademicTerm, id=term_id, school=school)

    context = _build_report_card_context(student, academic_term, school)
    context['page_title'] = f'Report Card - {student}'
    return render(request, 'hod_template/report_card_template.html', context)


def report_card_pdf(request, student_id, term_id):
    """Export report card as PDF - matches display/print layout."""
    if not REPORTLAB_AVAILABLE:
        messages.error(request, "PDF export requires reportlab. Install with: pip install reportlab")
        return redirect('report_card_list')

    school = _get_school_from_request(request)
    if not school:
        return HttpResponse("School context required.", status=403)

    student = get_object_or_404(Student, id=student_id, admin__school=school)
    academic_term = get_object_or_404(AcademicTerm, id=term_id, school=school)

    context = _build_report_card_context(student, academic_term, school)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="report_card_{student.admission_number}_{academic_term.academic_year}_{academic_term.term_name}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    settings_obj = context['settings']
    school_obj = school
    school_class = student.get_class_info() or student.current_class

    # Centered styles
    center_style = ParagraphStyle('Center', parent=styles['Normal'], alignment=TA_CENTER)
    title_style = ParagraphStyle('SchoolTitle', parent=styles['Title'], alignment=TA_CENTER, fontSize=18)

    # Header - logo, school name, address, tel
    if settings_obj and settings_obj.school_logo:
        try:
            logo_path = settings_obj.school_logo.path
            img = Image(logo_path, width=1.2*inch, height=1.2*inch)
            story.append(Paragraph('<br/>', styles['Normal']))
            story.append(img)
        except Exception:
            story.append(Paragraph('[School Logo]', ParagraphStyle('LogoPlaceholder', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.grey)))
    elif school_obj and school_obj.logo:
        try:
            logo_path = school_obj.logo.path
            img = Image(logo_path, width=1.2*inch, height=1.2*inch)
            story.append(img)
        except Exception:
            story.append(Paragraph('[School Logo]', ParagraphStyle('LogoPlaceholder', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.grey)))
    else:
        story.append(Paragraph('[School Logo]', ParagraphStyle('LogoPlaceholder', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.grey)))

    school_name = (settings_obj.school_name if settings_obj else None) or (school_obj.name if school_obj else "School")
    story.append(Paragraph(school_name, title_style))
    story.append(Paragraph(settings_obj.school_address or school_obj.address or "", center_style))
    story.append(Paragraph(f"Tel: {settings_obj.school_phone or school_obj.phone or ''}", center_style))
    story.append(Spacer(1, 0.2*inch))

    # ACADEMIC REPORT CARD title
    story.append(Paragraph("ACADEMIC REPORT CARD", ParagraphStyle('ReportTitle', parent=styles['Heading2'], alignment=TA_CENTER, fontSize=14)))
    story.append(Paragraph(f"Academic Year: {academic_term.academic_year} | Term: {academic_term.term_name}", center_style))
    story.append(Spacer(1, 0.2*inch))

    # Student info - two columns: Left (Name, Class, Gender) | Right (Admission No, Stream, Term)
    student_name = f"{student.admin.last_name}, {student.admin.first_name}"
    stream_name = school_class.stream.name if school_class and school_class.stream else "-"
    class_name = school_class.name if school_class else "-"
    left_col = f"<b>Student Name:</b> {student_name}<br/><b>Class:</b> {class_name}<br/><b>Gender:</b> {student.admin.gender or '-'}"
    right_col = f"<b>Admission No:</b> {student.admission_number or '-'}<br/><b>Stream:</b> {stream_name}<br/><b>Term:</b> {academic_term.term_name}"
    student_data = [[Paragraph(left_col, styles['Normal']), Paragraph(right_col, styles['Normal'])]]
    student_table = Table(student_data, colWidths=[200, 200])
    student_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(student_table)
    story.append(Spacer(1, 0.2*inch))

    # Results table
    data = [['Subject', 'Opener', 'Midterm', 'Endterm', 'Average', 'Grade', 'Points', 'Remarks']]
    for r in context['results']:
        data.append([
            r.subject.name,
            str(int(r.opener_marks)) if r.opener_marks else '0',
            str(int(r.midterm_marks)) if r.midterm_marks else '0',
            str(int(r.endterm_marks)) if r.endterm_marks else '0',
            str(round(r.average, 1)),
            r.grade or '-',
            str(int(r.points)) if r.points else '-',
            r.remarks or '-',
        ])
    if data:
        t = Table(data, colWidths=[80, 45, 45, 45, 45, 35, 35, 70])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.2*inch))

    # Summary section
    summary_text = f"<b>Summary:</b> Total Points: {context['total_points']:.1f} | Total Subjects: {context['total_subjects']} | Mean Score: {context['mean_score']} | Mean Grade: {context['mean_grade']} | Position in Class: {context['position_in_class'] or '-'}"
    story.append(Paragraph(summary_text, styles['Normal']))
    story.append(Spacer(1, 0.15*inch))

    # Comments section
    story.append(Paragraph("<b>Class Teacher Comment:</b> _________________________", styles['Normal']))
    story.append(Paragraph("<b>Head Teacher Comment:</b> _________________________", styles['Normal']))
    story.append(Paragraph("<b>Student Conduct:</b> _________________________", styles['Normal']))
    story.append(Spacer(1, 0.15*inch))

    # Attendance section
    story.append(Paragraph(f"<b>Attendance:</b> Days Open: {context['days_open']} | Days Present: {context['days_present']} | Days Absent: {context['days_absent']}", styles['Normal']))

    doc.build(story)
    return response


def knec_enter_marks(request):
    """Enter KNEC marks (Opener, Midterm, Endterm) per class and term."""
    school = _get_school_from_request(request)
    if not school:
        messages.warning(request, "School context required.")
        return redirect('admin_home')

    academic_terms = AcademicTerm.objects.filter(school=school).order_by('-academic_year', 'term_name')
    courses = Course.objects.filter(school=school, is_active=True).order_by('name')

    term_id = request.GET.get('term')
    class_id = request.GET.get('course') or request.GET.get('class')  # 'course' preferred; 'class' for backward compat
    subject_id = request.GET.get('subject')

    if request.method == 'POST':
        term_id = request.POST.get('academic_term')
        class_id = request.POST.get('school_class')
        subject_id = request.POST.get('subject')
        academic_term = get_object_or_404(AcademicTerm, id=term_id, school=school)
        school_class = get_object_or_404(Course, id=class_id, school=school)
        subject = get_object_or_404(Subject, id=subject_id, course=school_class)

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
                        v = float(val) if val else 0
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
        messages.success(request, "Marks saved successfully.")
        return redirect(reverse('knec_enter_marks') + f'?term={term_id}&course={class_id}&subject={subject_id}')

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
            enrollments = StudentClassEnrollment.objects.filter(
                school_class=selected_class, status='active',
                student__admin__school=school
            ).select_related('student__admin')
            for enr in enrollments:
                res = KNECReportCardResult.objects.filter(
                    student=enr.student, subject=selected_subject, academic_term=selected_term
                ).first()
                students.append({
                    'student': enr.student,
                    'result': res,
                })

    context = {
        'page_title': 'Enter Students Marks',
        'academic_terms': academic_terms,
        'courses': courses,
        'subjects': subjects,
        'students': students,
        'selected_term': selected_term,
        'selected_class': selected_class,
        'selected_subject': selected_subject,
        'term_id': term_id,
        'class_id': class_id,
        'subject_id': subject_id,
    }
    return render(request, 'hod_template/knec_enter_marks.html', context)

"""
Kenyan KNEC-based Report Card views.
Supports Opener, Midterm, End-Term exams with automatic grade calculation.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone

from .models import (
    KNECReportCardResult, Student, Subject, Course, AcademicTerm, Session,
    ClassAttendance, ClassAttendanceRecord, StudentClassEnrollment,
    SchoolSettings, School
)
from .knec_utils import get_knec_grade, get_mean_grade_from_points
from .grade_utils import get_grade_for_marks, get_mean_grade_from_points_school
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
        # Compute rankings (position in class by total points)
        student_ids = [e.student_id for e in enrollments]
        rank_data = list(
            KNECReportCardResult.objects.filter(
                student_id__in=student_ids,
                academic_term=selected_term
            ).values('student_id')
            .annotate(total_points=Sum('points'))
        )
        rank_map = {sid: 0 for sid in student_ids}
        for r in rank_data:
            rank_map[r['student_id']] = r['total_points'] or 0
        sorted_students = sorted(rank_map.items(), key=lambda x: x[1], reverse=True)
        position_map = {sid: i + 1 for i, (sid, _) in enumerate(sorted_students)}

        for enr in enrollments:
            results = KNECReportCardResult.objects.filter(
                student=enr.student, academic_term=selected_term
            ).count()
            students.append({
                'enrollment': enr,
                'student': enr.student,
                'has_results': results > 0,
                'result_count': results,
                'position_in_class': position_map.get(enr.student_id),
                'total_in_class': len(enrollments),
            })

        # Class & term averages, pass/fail stats
        class_stats = _compute_class_term_stats(selected_class, selected_term, school, enrollments)

    else:
        class_stats = None

    context = {
        'page_title': 'Report Cards',
        'academic_terms': academic_terms,
        'courses': courses,
        'students': students,
        'selected_term': selected_term,
        'selected_class': selected_class,
        'term_id': term_id,
        'class_id': class_id,
        'class_stats': class_stats,
        'reportlab_available': REPORTLAB_AVAILABLE,
    }
    return render(request, 'hod_template/report_card_list.html', context)


def _compute_class_term_stats(school_class, academic_term, school, enrollments):
    """Compute class averages, subject averages, and pass/fail percentages."""
    student_ids = [e.student_id for e in enrollments]
    results_qs = KNECReportCardResult.objects.filter(
        student_id__in=student_ids,
        academic_term=academic_term
    ).select_related('subject')

    # Per-subject class average
    subject_avgs = list(
        results_qs.values('subject__name', 'subject_id')
        .annotate(avg_marks=Avg('average'))
        .order_by('subject__name')
    )

    # Per-student total average (for pass/fail)
    student_totals = {}
    for r in results_qs:
        sid = r.student_id
        if sid not in student_totals:
            student_totals[sid] = []
        student_totals[sid].append(r.average or 0)

    pass_count = 0
    fail_count = 0
    total_avg_sum = 0
    student_count_with_results = 0
    for sid, avgs in student_totals.items():
        if not avgs:
            continue
        mean = sum(avgs) / len(avgs)
        total_avg_sum += mean
        student_count_with_results += 1
        if mean >= 50:
            pass_count += 1
        else:
            fail_count += 1

    overall_class_avg = round(total_avg_sum / student_count_with_results, 1) if student_count_with_results else 0
    total_students = pass_count + fail_count
    pass_pct = round(100 * pass_count / total_students, 1) if total_students else 0
    fail_pct = round(100 * fail_count / total_students, 1) if total_students else 0

    return {
        'overall_class_avg': overall_class_avg,
        'subject_averages': subject_avgs,
        'pass_count': pass_count,
        'fail_count': fail_count,
        'pass_pct': pass_pct,
        'fail_pct': fail_pct,
        'total_students_with_results': total_students,
    }


def _build_report_card_context(student, academic_term, school):
    """Build context for a single student's report card (Assessment Report format)."""
    settings_obj = get_school_settings(school)
    school_obj = school

    results_qs = KNECReportCardResult.objects.filter(
        student=student, academic_term=academic_term
    ).select_related('subject').order_by('subject__name')

    # Enrich results with per-exam grades (opener, midterm, endterm each have own grade)
    results = []
    total_opener = total_midterm = total_endterm = total_avg = 0
    for r in results_qs:
        og, _, _ = get_grade_for_marks(r.opener_marks or 0, school)
        mg, _, _ = get_grade_for_marks(r.midterm_marks or 0, school)
        eg, _, _ = get_grade_for_marks(r.endterm_marks or 0, school)
        results.append({
            'subject': r.subject,
            'opener_marks': r.opener_marks or 0,
            'midterm_marks': r.midterm_marks or 0,
            'endterm_marks': r.endterm_marks or 0,
            'average': r.average,
            'opener_grade': og or '-',
            'midterm_grade': mg or '-',
            'endterm_grade': eg or '-',
            'grade': r.grade or '-',
            'remarks': r.get_display_comment(),
            'teacher_initials': r.get_teacher_initials(),
        })
        total_opener += r.opener_marks or 0
        total_midterm += r.midterm_marks or 0
        total_endterm += r.endterm_marks or 0
        total_avg += r.average or 0

    total_subjects = len(results)
    mean_score = round((sum(r['average'] for r in results) / total_subjects), 2) if total_subjects else 0
    total_points = sum(get_grade_for_marks(r['average'], school)[1] for r in results) if results else 0
    mean_grade = get_mean_grade_from_points_school(total_points / total_subjects, school) if total_subjects else 'E'
    avg_opener = round(total_opener / total_subjects, 2) if total_subjects else 0
    avg_midterm = round(total_midterm / total_subjects, 2) if total_subjects else 0
    avg_endterm = round(total_endterm / total_subjects, 2) if total_subjects else 0
    avg_opener_grade = get_grade_for_marks(avg_opener, school)[0] or '-'
    avg_midterm_grade = get_grade_for_marks(avg_midterm, school)[0] or '-'
    avg_endterm_grade = get_grade_for_marks(avg_endterm, school)[0] or '-'

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
    total_in_class = len(enrollments)

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

    # Next term opening
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
        'mean_score': mean_score,
        'mean_grade': mean_grade,
        'position_in_class': position,
        'total_in_class': total_in_class,
        'total_opener': total_opener,
        'total_midterm': total_midterm,
        'total_endterm': total_endterm,
        'total_average': total_avg,
        'avg_opener': avg_opener,
        'avg_midterm': avg_midterm,
        'avg_endterm': avg_endterm,
        'avg_opener_grade': avg_opener_grade,
        'avg_midterm_grade': avg_midterm_grade,
        'avg_endterm_grade': avg_endterm_grade,
        'days_open': days_open,
        'days_present': days_present,
        'days_absent': days_absent,
        'next_term_opening': next_term_opening,
        'school': school_obj,
        'settings': settings_obj,
        'class_teacher_comment': '',
        'head_teacher_comment': '',
        'parent_comment': '',
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


def _generate_report_card_pdf_response(student, academic_term, school):
    """
    Generate PDF HttpResponse for a report card.
    Used by admin report_card_pdf and parent_download_knec_report_card_pdf.
    """
    if not REPORTLAB_AVAILABLE:
        return None
    context = _build_report_card_context(student, academic_term, school)
    response = HttpResponse(content_type='application/pdf')
    safe_name = f"{student.admin.first_name}_{student.admin.last_name}_{academic_term.academic_year}_{academic_term.term_name}_reportForm".replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.pdf"'

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
    story.append(Paragraph(school_name.upper(), title_style))
    if settings_obj.school_address or (school_obj and school_obj.address):
        story.append(Paragraph(settings_obj.school_address or school_obj.address or "", center_style))
    if settings_obj.school_motto:
        story.append(Paragraph(f"Motto: {settings_obj.school_motto}", ParagraphStyle('Motto', parent=styles['Normal'], alignment=TA_CENTER, fontName='Helvetica-Oblique')))
    story.append(Spacer(1, 0.15*inch))

    # Assessment Report title
    story.append(Paragraph("Assessment Report", ParagraphStyle('ReportTitle', parent=styles['Heading2'], alignment=TA_CENTER, fontSize=14)))
    story.append(Spacer(1, 0.15*inch))

    # Student info: NAME, Adm No, CLASS, STREAM, TERM, YEAR
    student_name = f"{student.admin.first_name} {student.admin.last_name}"
    school_class = context.get('school_class')
    class_name = school_class.name if school_class else '-'
    stream_name = school_class.stream.name if school_class and school_class.stream else '-'
    story.append(Paragraph(f"<b>NAME:</b> {student_name}  <b>Adm No:</b> {student.admission_number or '-'}  <b>CLASS:</b> {class_name}  <b>STREAM:</b> {stream_name}", styles['Normal']))
    story.append(Paragraph(f"<b>TERM:</b> {academic_term.academic_year} {academic_term.term_name}  <b>SESSION:</b> {academic_term.academic_year}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))

    # Results table: #, SUBJECT, OPENER (%, Grade), MID TERM (%, Grade), END TERM (%, Grade), AVERAGE (%, Grade), COMMENTS, TEACHER'S INITIALS
    data = [
        ['#', 'SUBJECT', 'OPENER %', 'Grade', 'MID %', 'Grade', 'END %', 'Grade', 'AVG %', 'Grade', 'COMMENTS', "TEACHER"]
    ]
    for i, r in enumerate(context['results'], 1):
        data.append([
            str(i), r['subject'].name,
            str(int(r['opener_marks'])), str(r['opener_grade']),
            str(int(r['midterm_marks'])), str(r['midterm_grade']),
            str(int(r['endterm_marks'])), str(r['endterm_grade']),
            str(int(r['average'])), str(r['grade']),
            r.get('remarks', ''), r.get('teacher_initials', '')
        ])
    if not context['results']:
        data.append(['', 'No results entered. Please enter marks first.', '', '', '', '', '', '', '', '', '', ''])
    else:
        # TOTAL MARKS row
        data.append([
            '', 'TOTAL MARKS',
            str(int(context['total_opener'])), '',
            str(int(context['total_midterm'])), '',
            str(int(context['total_endterm'])), '',
            str(int(context['total_average'])), '',
            '', ''
        ])
        # AVERAGE row
        data.append([
            '', 'AVERAGE',
            str(int(context['avg_opener'])), str(context['avg_opener_grade']),
            str(int(context['avg_midterm'])), str(context['avg_midterm_grade']),
            str(int(context['avg_endterm'])), str(context['avg_endterm_grade']),
            str(int(context['mean_score'])), str(context['mean_grade']),
            '', ''
        ])
        col_widths = [18, 70, 28, 22, 32, 22, 32, 22, 32, 22, 45, 35]
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.2*inch))

    # Class position
    story.append(Paragraph(f"<b>Class position:</b> {context['position_in_class'] or '-'} Out Of {context['total_in_class'] or '-'}", styles['Normal']))
    story.append(Spacer(1, 0.15*inch))

    # Comments section
    story.append(Paragraph("<b>CLASS TEACHER'S COMMENT:</b> _________________________", styles['Normal']))
    story.append(Paragraph("SIGNATURE: .................. DATE: ....................", ParagraphStyle('Small', parent=styles['Normal'], fontSize=9)))
    story.append(Paragraph("<b>PRINCIPAL'S COMMENT:</b> _________________________", styles['Normal']))
    story.append(Paragraph("SIGNATURE: .................. DATE: ....................", ParagraphStyle('Small', parent=styles['Normal'], fontSize=9)))
    story.append(Paragraph("<b>PARENT'S COMMENT:</b> _________________________", styles['Normal']))
    story.append(Paragraph("SIGNATURE: .................. DATE: ....................", ParagraphStyle('Small', parent=styles['Normal'], fontSize=9)))
    story.append(Spacer(1, 0.15*inch))

    # Opening and Closing dates
    if academic_term.start_date and academic_term.end_date:
        story.append(Paragraph(f"<b>OPENING DATE:</b> {academic_term.start_date.strftime('%d-%m-%Y')}    <b>CLOSING DATE:</b> {academic_term.end_date.strftime('%d-%m-%Y')}", styles['Normal']))
        story.append(Spacer(1, 0.15*inch))

    # Grading Key
    story.append(Paragraph("<b>KEY</b>  A - Very Good   B - Good   C - Fair   D - Weak   E - Poor", ParagraphStyle('Key', parent=styles['Normal'], fontSize=9)))

    doc.build(story)
    return response


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

    response = _generate_report_card_pdf_response(student, academic_term, school)
    return response if response else redirect('report_card_list')


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

"""
MVP: Controlled Teacher Result Upload Permission
Teachers can ONLY edit/upload results when admin explicitly opens the result entry window.
"""
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.shortcuts import render


def can_teacher_enter_legacy_results(request, session_id=None):
    """
    Check if teacher can enter legacy results (staff_add_result, edit_student_result).
    Uses ResultEntryWindow - at least one must be open.
    If session_id given, window must match that session.
    """
    from .models import ResultEntryWindow, AcademicTerm
    today = timezone.now().date()
    qs = ResultEntryWindow.objects.filter(
        result_entry_open=True,
        status='open'
    ).select_related('session', 'academic_term')
    if session_id:
        qs = qs.filter(session_id=session_id)
    for w in qs:
        if w.academic_term and w.academic_term.status == 'closed':
            continue
        if w.result_entry_start_date and today < w.result_entry_start_date:
            continue
        if w.result_entry_end_date and today > w.result_entry_end_date:
            continue
        return True
    return False


def can_teacher_enter_exam_results(request, exam_schedule):
    """
    Check if teacher can enter exam results for this ExamSchedule.
    """
    if not exam_schedule:
        return False
    return exam_schedule.is_result_entry_allowed()


def can_teacher_enter_cat_marks(request):
    """
    Check if teacher can enter CAT marks.
    Uses active term - if term is closed, no entry.
    """
    from .models import AcademicTerm
    school = getattr(request, 'school', None)
    active_term = AcademicTerm.get_active_term(school=school)
    if not active_term:
        return False
    if active_term.status == 'closed':
        return False
    return True


def require_result_entry_permission(view_func):
    """
    Decorator for staff result entry views.
    Returns 403 if result entry is closed.
    """
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser or request.user.user_type == '1':
            return view_func(request, *args, **kwargs)
        if not can_teacher_enter_legacy_results(request):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accepts('application/json'):
                return HttpResponseForbidden("Result upload is currently closed. Please contact the administrator.")
            return render(request, 'staff_template/result_entry_closed.html', {
                'page_title': 'Result Entry Closed',
                'message': 'Result upload is currently closed. Please contact the administrator.'
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

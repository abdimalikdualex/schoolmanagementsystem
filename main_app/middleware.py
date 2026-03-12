from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin
from django.urls import reverse
from django.shortcuts import redirect


class SchoolContextMiddleware(MiddlewareMixin):
    """Set request.school for multi-tenant data isolation. Super Admin has school=None.
    Blocks access for school users whose school is not approved (pending/rejected/suspended)."""
    def process_request(self, request):
        request.school = None
        if request.user.is_authenticated and hasattr(request.user, 'school'):
            school = getattr(request.user, 'school', None)
            # Super Admin has no school - allow
            if school is None:
                return None
            # School user - must have approved school
            if school.status != 'approved':
                from django.contrib.auth import logout
                logout(request)
                from django.contrib import messages
                messages.error(
                    request,
                    "Your school access has been suspended or is pending approval. "
                    "Contact the platform administrator."
                )
                return redirect(reverse('login_page'))
            request.school = school
        return None


class LoginCheckMiddleWare(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user # Who is the current user ?
        if user.is_authenticated:
            # Super Admin (user_type='0' or is_superuser) - platform owner, only super_admin views
            if str(user.user_type) == '0' or user.is_superuser:
                url_name = request.resolver_match.url_name if request.resolver_match else None
                if url_name == 'user_logout':
                    return None  # Allow logout
                if modulename != 'main_app.super_admin_views':
                    return redirect(reverse('super_admin_dashboard'))
                return None
            # Finance Officer (user_type='5') - ONLY finance URLs allowed
            if str(user.user_type) == '5':
                # Allow static/media assets
                if request.path.startswith('/static/') or request.path.startswith('/media/'):
                    return None
                from main_app.finance_urls import FINANCE_OFFICER_ALLOWED_URL_NAMES
                url_name = request.resolver_match.url_name if request.resolver_match else None
                if url_name not in FINANCE_OFFICER_ALLOWED_URL_NAMES:
                    return HttpResponseForbidden("Insufficient Permissions")
                return None  # Allow - continue to view
            # Admission Officer (user_type='6') - ONLY admission URLs allowed
            if str(user.user_type) == '6':
                if request.path.startswith('/static/') or request.path.startswith('/media/'):
                    return None
                from main_app.admission_urls import ADMISSION_OFFICER_ALLOWED_URL_NAMES
                url_name = request.resolver_match.url_name if request.resolver_match else None
                if url_name not in ADMISSION_OFFICER_ALLOWED_URL_NAMES:
                    return HttpResponseForbidden("Insufficient Permissions")
                return None
            if user.user_type == '1': # Is it the HOD/Admin
                if modulename == 'main_app.student_views' or modulename == 'main_app.parent_views':
                    return redirect(reverse('admin_home'))
            elif user.user_type == '2': # Staff (teachers)
                if modulename == 'main_app.student_views' or modulename == 'main_app.parent_views':
                    return redirect(reverse('staff_home'))
                # Allow staff to access specific hod_views for Examinations (enter marks, submit, view)
                # Result Submission Status is admin-only - teachers just enter marks and submit
                if modulename == 'main_app.hod_views':
                    STAFF_ALLOWED_HOD_URLS = {
                        'enter_cat_marks', 'enter_exam_results', 'teacher_submit_results',
                        'view_exam_results', 'delete_knec_result',
                    }
                    url_name = request.resolver_match.url_name if request.resolver_match else None
                    if url_name not in STAFF_ALLOWED_HOD_URLS:
                        return redirect(reverse('staff_home'))
            elif user.user_type == '3': # ... or Student ?
                if modulename == 'main_app.hod_views' or modulename == 'main_app.staff_views' or modulename == 'main_app.parent_views':
                    return redirect(reverse('student_home'))
            elif user.user_type == '4': # Parent
                if modulename == 'main_app.hod_views' or modulename == 'main_app.staff_views' or modulename == 'main_app.student_views':
                    return redirect(reverse('parent_home'))
            else: # None of the aforementioned ? Please take the user to login page
                return redirect(reverse('login_page'))
        else:
            # Allow unauthenticated access to login, registration, and static/media
            url_name = request.resolver_match.url_name if request.resolver_match else None
            if (request.path == reverse('login_page') or request.path == reverse('user_login') or
                    url_name == 'school_registration' or url_name == 'verify_email' or
                    modulename == 'django.contrib.auth.views' or
                    request.path.startswith('/static/') or request.path.startswith('/media/')):
                pass
            else:
                return redirect(reverse('login_page'))

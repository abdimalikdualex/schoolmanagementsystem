from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin
from django.urls import reverse
from django.shortcuts import redirect


class LoginCheckMiddleWare(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        modulename = view_func.__module__
        user = request.user # Who is the current user ?
        if user.is_authenticated:
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
            if user.user_type == '1': # Is it the HOD/Admin
                if modulename == 'main_app.student_views' or modulename == 'main_app.parent_views':
                    return redirect(reverse('admin_home'))
            elif user.user_type == '2': #  Staff :-/ ?
                if modulename == 'main_app.student_views' or modulename == 'main_app.hod_views' or modulename == 'main_app.parent_views':
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
            if request.path == reverse('login_page') or modulename == 'django.contrib.auth.views' or request.path == reverse('user_login'): # If the path is login or has anything to do with authentication, pass
                pass
            else:
                return redirect(reverse('login_page'))

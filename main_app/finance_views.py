"""
Finance Officer views - restricted to finance-only operations.
All views in this module are for user_type='5' (Finance Officer).
"""
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import FeeBalance, Session


def finance_officer_required(view_func):
    """Decorator: ensure user is Finance Officer. Returns 403 otherwise."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_page')
        if str(request.user.user_type) != '5':
            return HttpResponseForbidden("Insufficient Permissions")
        return view_func(request, *args, **kwargs)
    return wrapper


@finance_officer_required
def finance_profile(request):
    """Finance Officer profile update"""
    user = request.user
    context = {
        'page_title': 'Profile',
        'user': user,
    }
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        address = request.POST.get('address', '').strip()
        gender = request.POST.get('gender', 'M')
        phone_number = request.POST.get('phone_number', '').strip() or None
        password = request.POST.get('password', '').strip() or None

        if first_name and last_name:
            user.first_name = first_name
            user.last_name = last_name
            user.address = address
            user.gender = gender
            user.phone_number = phone_number
            if password:
                user.set_password(password)
            passport = request.FILES.get('profile_pic')
            if passport:
                fs = FileSystemStorage()
                filename = fs.save(passport.name, passport)
                user.profile_pic = fs.url(filename)
            user.save()
            messages.success(request, "Profile Updated!")
            return redirect('finance_profile')
        else:
            messages.error(request, "First name and last name are required")
    return render(request, 'finance_template/finance_profile.html', context)


@finance_officer_required
def finance_student_billing(request):
    """Student billing - view students with fee status (school-scoped)"""
    school = getattr(request, 'school', None)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session_id = request.GET.get('session_id')
    session = session_qs.filter(id=session_id).first() if session_id else session_qs.order_by('-start_year').first()
    sessions = session_qs.order_by('-start_year').all()

    if not session:
        context = {
            'session': None,
            'sessions': sessions,
            'students_billing': [],
            'page_title': 'Student Billing',
        }
        return render(request, 'finance_template/finance_student_billing.html', context)

    # Get fee balances for this session (school-scoped)
    balances = FeeBalance.objects.filter(session=session).select_related(
        'student__admin', 'student__course'
    ).order_by('student__admin__last_name')
    if school:
        balances = balances.filter(student__admin__school=school)

    context = {
        'session': session,
        'sessions': sessions,
        'students_billing': balances,
        'page_title': 'Student Billing',
    }
    return render(request, 'finance_template/finance_student_billing.html', context)


@finance_officer_required
def finance_defaulters(request):
    """Defaulters list - students with unpaid balances (school-scoped)"""
    school = getattr(request, 'school', None)
    session_qs = Session.objects.filter(school=school) if school else Session.objects.all()
    session_id = request.GET.get('session_id')
    session = session_qs.filter(id=session_id).first() if session_id else session_qs.order_by('-start_year').first()
    sessions = session_qs.order_by('-start_year').all()

    if not session:
        defaulters = []
    else:
        defaulters = FeeBalance.objects.filter(
            session=session, balance__gt=0
        ).select_related('student__admin', 'student__course').order_by('-balance')
        if school:
            defaulters = defaulters.filter(student__admin__school=school)

    context = {
        'session': session,
        'sessions': sessions,
        'defaulters': defaulters,
        'page_title': 'Defaulters',
    }
    return render(request, 'finance_template/finance_defaulters.html', context)

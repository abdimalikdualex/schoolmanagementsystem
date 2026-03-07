"""
Super Admin views - platform owner managing multiple schools.
Only accessible when user_type='0' (Super Admin) or is_superuser.
"""
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import School, Student, Staff, SubscriptionPlan, CustomUser, SchoolSettings


def super_admin_required(view_func):
    """Decorator: ensure user is Super Admin. Returns 403 otherwise."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_page')
        if str(request.user.user_type) != '0' and not request.user.is_superuser:
            return HttpResponseForbidden("Insufficient Permissions - Super Admin only")
        return view_func(request, *args, **kwargs)
    return wrapper


@super_admin_required
def super_admin_dashboard(request):
    """Super Admin Dashboard - school list, approvals, platform statistics"""
    school_list = []
    for s in School.objects.all().order_by('-created_at'):
        students = Student.objects.filter(admin__school=s).count()
        teachers = Staff.objects.filter(admin__school=s).count()
        school_list.append({
            'school': s,
            'student_count': students,
            'teacher_count': teachers,
        })

    total_schools = School.objects.count()
    active_schools = School.objects.filter(status='approved').count()
    pending_approvals = School.objects.filter(status='pending').count()
    total_students = Student.objects.filter(admin__school__isnull=False).count()
    total_teachers = Staff.objects.filter(admin__school__isnull=False).count()

    context = {
        'page_title': 'Platform Owner Dashboard',
        'school_list': school_list,
        'total_schools': total_schools,
        'active_schools': active_schools,
        'pending_approvals': pending_approvals,
        'total_students': total_students,
        'total_teachers': total_teachers,
    }
    return render(request, 'super_admin_template/super_admin_dashboard.html', context)


@super_admin_required
def super_admin_create_school(request):
    """Create a new school"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        email = request.POST.get('email', '').strip() or None
        phone = request.POST.get('phone', '').strip() or None
        address = request.POST.get('address', '').strip() or None

        if not name or not code:
            messages.error(request, "Name and code are required.")
            return redirect('super_admin_create_school')

        if School.objects.filter(code=code).exists():
            messages.error(request, f"School with code '{code}' already exists.")
            return redirect('super_admin_create_school')

        plan_id = request.POST.get('subscription_plan')
        plan = SubscriptionPlan.objects.filter(pk=plan_id).first() if plan_id else None

        school = School.objects.create(
            name=name,
            code=code,
            email=email,
            phone=phone,
            address=address,
            subscription_plan=plan,
            is_active=True,
        )
        SchoolSettings.objects.get_or_create(
            school=school,
            defaults={'school_name': name, 'school_email': email or '', 'school_phone': phone or '', 'school_address': address or ''}
        )
        messages.success(request, f"School '{name}' created successfully.")
        return redirect('super_admin_dashboard')

    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('student_limit')
    context = {'page_title': 'Create School', 'plans': plans}
    return render(request, 'super_admin_template/super_admin_create_school.html', context)


@super_admin_required
def super_admin_edit_school(request, school_id):
    """Edit a school"""
    school = get_object_or_404(School, id=school_id)
    if request.method == 'POST':
        school.name = request.POST.get('name', '').strip() or school.name
        code = request.POST.get('code', '').strip().upper()
        if code and code != school.code:
            if School.objects.filter(code=code).exclude(pk=school.pk).exists():
                messages.error(request, f"School with code '{code}' already exists.")
                return redirect('super_admin_edit_school', school_id=school_id)
            school.code = code
        school.email = request.POST.get('email', '').strip() or None
        school.phone = request.POST.get('phone', '').strip() or None
        school.address = request.POST.get('address', '').strip() or None
        status = request.POST.get('status')
        if status in ('pending', 'approved', 'rejected', 'suspended'):
            school.status = status
        plan_id = request.POST.get('subscription_plan')
        if plan_id:
            school.subscription_plan = SubscriptionPlan.objects.filter(pk=plan_id).first()
        else:
            school.subscription_plan = None
        school.is_active = request.POST.get('is_active') == 'on'
        school.save()
        messages.success(request, f"School '{school.name}' updated.")
        return redirect('super_admin_dashboard')

    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('student_limit')
    context = {'page_title': 'Edit School', 'school': school, 'plans': plans}
    return render(request, 'super_admin_template/super_admin_edit_school.html', context)


@super_admin_required
def super_admin_approve_school(request, school_id):
    """Approve a school - allows them to access the system"""
    school = get_object_or_404(School, id=school_id)
    school.status = 'approved'
    school.is_active = True
    school.save()
    messages.success(request, f"School '{school.name}' has been approved. They can now log in.")
    return redirect('super_admin_dashboard')


@super_admin_required
def super_admin_reject_school(request, school_id):
    """Reject a school registration"""
    school = get_object_or_404(School, id=school_id)
    school.status = 'rejected'
    school.save()
    messages.success(request, f"School '{school.name}' has been rejected.")
    return redirect('super_admin_dashboard')


@super_admin_required
def super_admin_suspend_school(request, school_id):
    """Suspend an approved school - blocks access"""
    school = get_object_or_404(School, id=school_id)
    school.status = 'suspended'
    school.save()
    messages.success(request, f"School '{school.name}' has been suspended. They can no longer access the system.")
    return redirect('super_admin_dashboard')


@super_admin_required
def super_admin_user_monitoring(request):
    """View all teachers, students, and admins across all schools."""
    user_type_filter = request.GET.get('type', '')  # '', '1', '2', '3', '4'
    school_filter = request.GET.get('school', '')

    users = CustomUser.objects.exclude(user_type='0').filter(school__isnull=False).select_related('school')
    if user_type_filter:
        users = users.filter(user_type=user_type_filter)
    if school_filter:
        users = users.filter(school_id=school_filter)

    users = users.order_by('school__name', 'last_name', 'first_name')[:500]  # Limit for performance

    schools = School.objects.filter(status='approved').order_by('name')
    context = {
        'page_title': 'User Monitoring',
        'users': users,
        'schools': schools,
        'user_type_filter': user_type_filter,
        'school_filter': school_filter,
    }
    return render(request, 'super_admin_template/super_admin_user_monitoring.html', context)


@super_admin_required
def super_admin_deactivate_school(request, school_id):
    """Deactivate a school (legacy - sets is_active=False)"""
    school = get_object_or_404(School, id=school_id)
    school.is_active = False
    school.save()
    messages.success(request, f"School '{school.name}' has been deactivated.")
    return redirect('super_admin_dashboard')

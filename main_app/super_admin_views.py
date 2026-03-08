"""
Super Admin views - platform owner managing multiple schools.
Only accessible when user_type='0' (Super Admin) or is_superuser.
"""
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from datetime import timedelta
from django.utils import timezone

from .models import School, Student, Staff, SubscriptionPlan, CustomUser, SchoolSettings, SchoolSubscription
from .email_service import send_school_approval_email


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
    suspended_schools = School.objects.filter(status='suspended').count()
    pending_approvals = School.objects.filter(status='pending').count()
    total_students = Student.objects.filter(admin__school__isnull=False).count()
    total_teachers = Staff.objects.filter(admin__school__isnull=False).count()

    context = {
        'page_title': 'Platform Owner Dashboard',
        'school_list': school_list,
        'total_schools': total_schools,
        'active_schools': active_schools,
        'suspended_schools': suspended_schools,
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
    """Approve a school - allows them to access the system. Sends approval email to school admin."""
    school = get_object_or_404(School, id=school_id)
    school.status = 'approved'
    school.is_active = True
    school.save()

    # Create SchoolSubscription if school has a plan and no active subscription
    if school.subscription_plan and not school.subscriptions.filter(active=True).exists():
        start = timezone.now().date()
        end = start + timedelta(days=365)  # 1 year default
        SchoolSubscription.objects.create(
            school=school,
            plan=school.subscription_plan,
            start_date=start,
            end_date=end,
            payment_status='pending',
            active=True,
        )

    admin_email = school.email
    admin_user = CustomUser.objects.filter(user_type='1', school=school).first()
    if admin_user:
        admin_email = admin_user.email
    if admin_email:
        login_url = request.build_absolute_uri(reverse('login_page'))
        send_school_approval_email(school, admin_email, login_url)
    messages.success(request, f"School '{school.name}' has been approved.")
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
def super_admin_reset_password(request, user_id):
    """System administrator resets a user's password (e.g. when admin forgets password)."""
    target_user = get_object_or_404(CustomUser, id=user_id)
    # Do not allow resetting super admin passwords via this view (security)
    if str(target_user.user_type) == '0' or target_user.is_superuser:
        messages.error(request, "Cannot reset Super Admin passwords via this page.")
        return redirect('super_admin_user_monitoring')

    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        if not new_password:
            messages.error(request, "Password cannot be empty.")
            return redirect('super_admin_reset_password', user_id=user_id)
        if len(new_password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
            return redirect('super_admin_reset_password', user_id=user_id)
        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect('super_admin_reset_password', user_id=user_id)
        target_user.set_password(new_password)
        target_user.save()
        messages.success(request, f"Password has been reset for {target_user.get_full_name() or target_user.email}.")
        return redirect('super_admin_user_monitoring')

    context = {
        'page_title': 'Reset Password',
        'target_user': target_user,
    }
    return render(request, 'super_admin_template/super_admin_reset_password.html', context)


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


@super_admin_required
def super_admin_delete_school(request, school_id):
    """Delete a school and all related data. Only platform owner. Requires confirmation."""
    school = get_object_or_404(School, id=school_id)
    school_name = school.name
    school.delete()  # CASCADE deletes related users, courses, etc.
    messages.success(request, f"School '{school_name}' and all related data have been permanently deleted.")
    return redirect('super_admin_dashboard')


@super_admin_required
def super_admin_view_school(request, school_id):
    """View school details - platform owner only"""
    school = get_object_or_404(School, id=school_id)
    students = Student.objects.filter(admin__school=school).count()
    teachers = Staff.objects.filter(admin__school=school).count()
    admins = CustomUser.objects.filter(user_type='1', school=school).count()
    active_subscription = school.subscriptions.filter(active=True).select_related('plan').first()
    context = {
        'page_title': f'School Details - {school.name}',
        'school': school,
        'student_count': students,
        'teacher_count': teachers,
        'admin_count': admins,
        'active_subscription': active_subscription,
    }
    return render(request, 'super_admin_template/super_admin_view_school.html', context)


@super_admin_required
def super_admin_manage_plans(request):
    """List subscription plans - platform owner only"""
    plans = SubscriptionPlan.objects.all().order_by('student_limit')
    context = {'page_title': 'Subscription Plans', 'plans': plans}
    return render(request, 'super_admin_template/super_admin_manage_plans.html', context)


@super_admin_required
def super_admin_create_plan(request):
    """Create a new subscription plan"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        student_limit = request.POST.get('student_limit', '0')
        teacher_limit = request.POST.get('teacher_limit', '0')
        monthly_price = request.POST.get('monthly_price', '0')
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, "Plan name is required.")
            return redirect('super_admin_create_plan')
        try:
            sl = int(student_limit) if student_limit else 0
            tl = int(teacher_limit) if teacher_limit else 0
            mp = float(monthly_price) if monthly_price else 0
        except (ValueError, TypeError):
            messages.error(request, "Invalid numbers for limits or price.")
            return redirect('super_admin_create_plan')
        if SubscriptionPlan.objects.filter(name=name).exists():
            messages.error(request, f"Plan '{name}' already exists.")
            return redirect('super_admin_create_plan')
        SubscriptionPlan.objects.create(
            name=name,
            student_limit=sl,
            teacher_limit=tl,
            monthly_price=mp,
            description=description or None,
            is_active=True,
        )
        messages.success(request, f"Plan '{name}' created successfully.")
        return redirect('super_admin_manage_plans')
    context = {'page_title': 'Create Subscription Plan'}
    return render(request, 'super_admin_template/super_admin_plan_form.html', context)


@super_admin_required
def super_admin_edit_plan(request, plan_id):
    """Edit a subscription plan"""
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    if request.method == 'POST':
        plan.name = request.POST.get('name', '').strip() or plan.name
        try:
            plan.student_limit = int(request.POST.get('student_limit', plan.student_limit) or 0)
            plan.teacher_limit = int(request.POST.get('teacher_limit', plan.teacher_limit) or 0)
            plan.monthly_price = float(request.POST.get('monthly_price', plan.monthly_price) or 0)
        except (ValueError, TypeError):
            messages.error(request, "Invalid numbers.")
            return redirect('super_admin_edit_plan', plan_id=plan_id)
        plan.description = request.POST.get('description', '').strip() or None
        plan.is_active = request.POST.get('is_active') == 'on'
        plan.save()
        messages.success(request, f"Plan '{plan.name}' updated.")
        return redirect('super_admin_manage_plans')
    context = {'page_title': f'Edit Plan - {plan.name}', 'plan': plan}
    return render(request, 'super_admin_template/super_admin_plan_form.html', context)

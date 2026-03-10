"""
SMS Service for sending results to students via SMS/STK Push
Supports multiple SMS providers: Africa's Talking, Twilio, Safaricom API
Enhanced with bulk SMS processing and queue management
"""
import os
import uuid
import requests
import json
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib import messages
from django.utils import timezone
from django.db import transaction

# SMS Provider Configuration
# Set these in your settings.py or environment variables
SMS_PROVIDER = getattr(settings, 'SMS_PROVIDER', 'africas_talking')  # Options: 'africas_talking', 'twilio', 'safaricom'

# Africa's Talking Configuration
AFRICAS_TALKING_API_KEY = getattr(settings, 'AFRICAS_TALKING_API_KEY', os.environ.get('AFRICAS_TALKING_API_KEY', ''))
AFRICAS_TALKING_USERNAME = getattr(settings, 'AFRICAS_TALKING_USERNAME', os.environ.get('AFRICAS_TALKING_USERNAME', ''))

# Twilio Configuration
TWILIO_ACCOUNT_SID = getattr(settings, 'TWILIO_ACCOUNT_SID', os.environ.get('TWILIO_ACCOUNT_SID', ''))
TWILIO_AUTH_TOKEN = getattr(settings, 'TWILIO_AUTH_TOKEN', os.environ.get('TWILIO_AUTH_TOKEN', ''))
TWILIO_PHONE_NUMBER = getattr(settings, 'TWILIO_PHONE_NUMBER', os.environ.get('TWILIO_PHONE_NUMBER', ''))

# Safaricom API Configuration
SAFARICOM_CONSUMER_KEY = getattr(settings, 'SAFARICOM_CONSUMER_KEY', os.environ.get('SAFARICOM_CONSUMER_KEY', ''))
SAFARICOM_CONSUMER_SECRET = getattr(settings, 'SAFARICOM_CONSUMER_SECRET', os.environ.get('SAFARICOM_CONSUMER_SECRET', ''))
SAFARICOM_SHORTCODE = getattr(settings, 'SAFARICOM_SHORTCODE', os.environ.get('SAFARICOM_SHORTCODE', ''))


def format_phone_number(phone):
    """
    Format phone number to international format (254XXXXXXXXX for Kenya)
    """
    if not phone:
        return None
    
    # Remove all non-digit characters
    phone = ''.join(filter(str.isdigit, str(phone)))
    
    # Handle different formats
    if phone.startswith('0'):
        # Convert 0712345678 to 254712345678
        phone = '254' + phone[1:]
    elif phone.startswith('+254'):
        # Convert +254712345678 to 254712345678
        phone = phone[1:]
    elif not phone.startswith('254'):
        # Assume it's a local number starting with 7
        if phone.startswith('7') and len(phone) == 9:
            phone = '254' + phone
    
    return phone if len(phone) == 12 else None


def send_sms_africas_talking(phone_number, message):
    """
    Send SMS using Africa's Talking API
    """
    try:
        phone_number = format_phone_number(phone_number)
        if not phone_number:
            return {'success': False, 'error': 'Invalid phone number format'}
        
        if not AFRICAS_TALKING_API_KEY or not AFRICAS_TALKING_USERNAME:
            return {'success': False, 'error': 'Africa\'s Talking API credentials not configured'}
        
        # Use sandbox URL for sandbox username, production URL otherwise
        if AFRICAS_TALKING_USERNAME == 'sandbox':
            url = "https://api.sandbox.africastalking.com/version1/messaging"
        else:
            url = "https://api.africastalking.com/version1/messaging"
        
        headers = {
            'ApiKey': AFRICAS_TALKING_API_KEY,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        # Build data - don't include 'from' for sandbox (use default)
        data = {
            'username': AFRICAS_TALKING_USERNAME,
            'to': f'+{phone_number}',  # Add + prefix for international format
            'message': message,
        }
        
        # Only add sender ID for production (registered sender IDs)
        if AFRICAS_TALKING_USERNAME != 'sandbox':
            # Get sender ID from school settings or use default
            school_settings = get_school_settings()
            if school_settings.sms_sender_id:
                data['from'] = school_settings.sms_sender_id
        
        response = requests.post(url, headers=headers, data=data)
        
        if response.status_code == 201:
            response_data = response.json()
            # Check if message was actually sent
            sms_data = response_data.get('SMSMessageData', {})
            recipients = sms_data.get('Recipients', [])
            
            if recipients:
                recipient = recipients[0]
                status = recipient.get('status', '')
                if status == 'Success':
                    return {
                        'success': True, 
                        'message': 'SMS sent successfully',
                        'message_id': recipient.get('messageId'),
                        'cost': recipient.get('cost')
                    }
                else:
                    return {
                        'success': False, 
                        'error': f"SMS failed: {recipient.get('status')} - {recipient.get('statusCode')}"
                    }
            else:
                return {'success': True, 'message': 'SMS queued', 'response': response_data}
        else:
            return {'success': False, 'error': f'API Error ({response.status_code}): {response.text}'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_sms_twilio(phone_number, message):
    """
    Send SMS using Twilio API
    """
    try:
        phone_number = format_phone_number(phone_number)
        if not phone_number:
            return {'success': False, 'error': 'Invalid phone number format'}
        
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            return {'success': False, 'error': 'Twilio API credentials not configured'}
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        data = {
            'From': TWILIO_PHONE_NUMBER,
            'To': f'+{phone_number}',
            'Body': message
        }
        
        response = requests.post(url, data=data, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
        
        if response.status_code == 201:
            return {'success': True, 'message': 'SMS sent successfully'}
        else:
            return {'success': False, 'error': f'API Error: {response.text}'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_sms_safaricom(phone_number, message):
    """
    Send SMS using Safaricom API (Daraja API)
    Note: This requires OAuth token first
    """
    try:
        phone_number = format_phone_number(phone_number)
        if not phone_number:
            return {'success': False, 'error': 'Invalid phone number format'}
        
        if not SAFARICOM_CONSUMER_KEY or not SAFARICOM_CONSUMER_SECRET:
            return {'success': False, 'error': 'Safaricom API credentials not configured'}
        
        # Get OAuth token
        token_url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        auth = (SAFARICOM_CONSUMER_KEY, SAFARICOM_CONSUMER_SECRET)
        token_response = requests.get(token_url, auth=auth)
        
        if token_response.status_code != 200:
            return {'success': False, 'error': 'Failed to get OAuth token'}
        
        access_token = token_response.json().get('access_token')
        
        # Send SMS
        url = "https://api.safaricom.co.ke/mpesa/b2c/v1/paymentrequest"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Note: Safaricom B2C API is for payments, not SMS
        # For SMS, you might need to use a different endpoint or service
        # This is a placeholder - you may need to use a different Safaricom SMS service
        return {'success': False, 'error': 'Safaricom SMS API endpoint needs to be configured'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_sms(phone_number, message):
    """
    Main function to send SMS using the configured provider
    """
    if SMS_PROVIDER == 'africas_talking':
        return send_sms_africas_talking(phone_number, message)
    elif SMS_PROVIDER == 'twilio':
        return send_sms_twilio(phone_number, message)
    elif SMS_PROVIDER == 'safaricom':
        return send_sms_safaricom(phone_number, message)
    else:
        return {'success': False, 'error': f'Unknown SMS provider: {SMS_PROVIDER}'}


def format_results_message(student, results):
    """
    Format student results into a concise SMS message
    """
    try:
        # Calculate totals
        total_marks = 0
        total_subjects = 0
        passed_subjects = 0
        
        results_text = []
        for result in results:
            total = result.test + result.exam
            total_marks += total
            total_subjects += 1
            
            # Determine grade
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
            
            if total >= 40:
                passed_subjects += 1
            
            # Short subject name (max 15 chars)
            subject_name = result.subject.name[:15]
            results_text.append(f"{subject_name}: {total}/100 ({grade})")
        
        average = round(total_marks / total_subjects, 1) if total_subjects > 0 else 0
        
        # Build message (SMS has 160 char limit, so keep it concise)
        message = f"SCHOOL MANAGEMENT SYSTEM\n"
        message += f"Results for {student.admin.first_name} {student.admin.last_name}\n"
        message += f"Reg: {student.admin.username}\n\n"
        
        # Add top 3 results if many subjects
        if len(results_text) > 3:
            message += "Top Results:\n"
            for i, res in enumerate(results_text[:3], 1):
                message += f"{i}. {res}\n"
            message += f"\nTotal: {total_marks}, Avg: {average}\n"
            message += f"Passed: {passed_subjects}/{total_subjects}"
        else:
            for i, res in enumerate(results_text, 1):
                message += f"{i}. {res}\n"
            message += f"\nTotal: {total_marks}, Avg: {average}\n"
            message += f"Passed: {passed_subjects}/{total_subjects}"
        
        message += f"\n\nStatus: {'PASS' if average >= 50 else 'FAIL'}"
        message += f"\nView full transcript online."
        
        return message
    
    except Exception as e:
        return f"Error formatting results: {str(e)}"


# ============================================
# BULK SMS AND QUEUE PROCESSING FUNCTIONS
# ============================================

def get_school_settings(school=None):
    """
    Get school settings for SMS/config. Multi-tenant: pass school for tenant-specific settings.
    When school is None, returns first available (legacy single-school or default).
    """
    from .models import SchoolSettings
    if school is not None:
        settings_obj = SchoolSettings.objects.filter(school=school).first()
    else:
        settings_obj = SchoolSettings.objects.first()
    if not settings_obj:
        settings_obj = SchoolSettings.objects.create(school_name="School Name", school=school)
    return settings_obj


def render_sms_template(template_content, context):
    """
    Render SMS template with context variables
    Available placeholders: {student_name}, {parent_name}, {class_name}, 
    {amount}, {date}, {school_name}, {balance}, {receipt_number}
    """
    try:
        for key, value in context.items():
            placeholder = "{" + key + "}"
            template_content = template_content.replace(placeholder, str(value))
        return template_content
    except Exception as e:
        return template_content


def add_to_sms_queue(phone_number, message, recipient_type='custom', recipient_id=None, 
                      template=None, scheduled_at=None, batch_id=None, created_by=None):
    """
    Add SMS to the queue for processing
    """
    from .models import SMSQueue
    
    phone_number = format_phone_number(phone_number)
    if not phone_number:
        return {'success': False, 'error': 'Invalid phone number'}
    
    try:
        sms = SMSQueue.objects.create(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            phone_number=phone_number,
            message=message,
            template=template,
            scheduled_at=scheduled_at,
            batch_id=batch_id or str(uuid.uuid4())[:8],
            created_by=created_by
        )
        return {'success': True, 'sms_id': sms.id, 'batch_id': sms.batch_id}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_bulk_sms_to_students(students, message, template=None, created_by=None):
    """
    Queue bulk SMS to multiple students
    """
    batch_id = str(uuid.uuid4())[:8]
    queued = 0
    errors = []
    
    for student in students:
        phone = student.admin.phone_number
        if not phone:
            errors.append(f"{student}: No phone number")
            continue
        
        # Personalize message
        context = {
            'student_name': f"{student.admin.first_name} {student.admin.last_name}",
            'class_name': str(student.course) if student.course else 'N/A',
            'admission_number': student.admission_number or 'N/A',
            'school_name': get_school_settings().school_name
        }
        personalized_msg = render_sms_template(message, context)
        
        result = add_to_sms_queue(
            phone_number=phone,
            message=personalized_msg,
            recipient_type='student',
            recipient_id=student.id,
            template=template,
            batch_id=batch_id,
            created_by=created_by
        )
        
        if result['success']:
            queued += 1
        else:
            errors.append(f"{student}: {result['error']}")
    
    return {
        'success': True,
        'batch_id': batch_id,
        'queued': queued,
        'errors': errors
    }


def send_bulk_sms_to_parents(students, message, template=None, created_by=None):
    """
    Queue bulk SMS to parents of students
    """
    from .models import Parent
    
    batch_id = str(uuid.uuid4())[:8]
    queued = 0
    errors = []
    
    for student in students:
        # Get parent(s) of this student
        parents = Parent.objects.filter(children=student)
        
        if not parents.exists():
            errors.append(f"{student}: No parent linked")
            continue
        
        for parent in parents:
            phone = parent.admin.phone_number
            if not phone:
                errors.append(f"Parent of {student}: No phone number")
                continue
            
            # Personalize message
            context = {
                'student_name': f"{student.admin.first_name} {student.admin.last_name}",
                'parent_name': f"{parent.admin.first_name} {parent.admin.last_name}",
                'class_name': str(student.course) if student.course else 'N/A',
                'school_name': get_school_settings().school_name
            }
            personalized_msg = render_sms_template(message, context)
            
            result = add_to_sms_queue(
                phone_number=phone,
                message=personalized_msg,
                recipient_type='parent',
                recipient_id=parent.id,
                template=template,
                batch_id=batch_id,
                created_by=created_by
            )
            
            if result['success']:
                queued += 1
            else:
                errors.append(f"Parent of {student}: {result['error']}")
    
    return {
        'success': True,
        'batch_id': batch_id,
        'queued': queued,
        'errors': errors
    }


def send_bulk_sms_to_class(course, message, include_parents=False, template=None, created_by=None):
    """
    Queue bulk SMS to all students in a class
    """
    from .models import Student, StudentClassEnrollment
    
    # Get students from enrollments or direct assignment
    enrolled_students = Student.objects.filter(
        enrollments__school_class=course,
        enrollments__status='active'
    ).distinct()
    
    direct_students = Student.objects.filter(course=course)
    students = (enrolled_students | direct_students).distinct()
    
    if include_parents:
        return send_bulk_sms_to_parents(students, message, template, created_by)
    else:
        return send_bulk_sms_to_students(students, message, template, created_by)


def process_sms_queue(batch_size=50, max_retries=3, school=None):
    """
    Process pending SMS in the queue. School-scoped for multi-tenant isolation.
    When school is provided, only processes that school's queue. Otherwise processes all (cron/legacy).
    """
    from .models import SMSQueue, SMSLog
    
    now = timezone.now()
    
    # Get pending SMS that are due (scheduled_at is null or past)
    pending_sms = SMSQueue.objects.filter(
        status='pending',
        retry_count__lt=max_retries
    ).filter(
        models.Q(scheduled_at__isnull=True) | models.Q(scheduled_at__lte=now)
    )
    if school:
        pending_sms = pending_sms.filter(created_by__school=school)
    pending_sms = pending_sms.order_by('created_at')[:batch_size]
    
    processed = 0
    success = 0
    failed = 0
    
    for sms in pending_sms:
        processed += 1
        sms.status = 'processing'
        sms.save()
        
        try:
            # Send SMS
            result = send_sms(sms.phone_number, sms.message)
            
            # Log the attempt
            SMSLog.objects.create(
                queue_item=sms,
                phone_number=sms.phone_number,
                message=sms.message,
                status='sent' if result['success'] else 'failed',
                provider=SMS_PROVIDER,
                response_data=result
            )
            
            if result['success']:
                sms.status = 'sent'
                sms.sent_at = timezone.now()
                success += 1
            else:
                sms.retry_count += 1
                if sms.retry_count >= max_retries:
                    sms.status = 'failed'
                else:
                    sms.status = 'pending'
                sms.error_message = result.get('error', 'Unknown error')
                failed += 1
            
            sms.save()
            
        except Exception as e:
            sms.retry_count += 1
            sms.error_message = str(e)
            if sms.retry_count >= max_retries:
                sms.status = 'failed'
            else:
                sms.status = 'pending'
            sms.save()
            failed += 1
            
            # Log the error
            SMSLog.objects.create(
                queue_item=sms,
                phone_number=sms.phone_number,
                message=sms.message,
                status='error',
                provider=SMS_PROVIDER,
                response_data={'error': str(e)}
            )
    
    return {
        'processed': processed,
        'success': success,
        'failed': failed
    }


def get_sms_queue_stats(batch_id=None, school=None):
    """
    Get statistics for SMS queue. School-scoped for multi-tenant isolation.
    """
    from .models import SMSQueue
    from django.db.models import Count
    
    queryset = SMSQueue.objects.all()
    if school:
        queryset = queryset.filter(created_by__school=school)
    if batch_id:
        queryset = queryset.filter(batch_id=batch_id)
    
    stats = queryset.values('status').annotate(count=Count('id'))
    
    result = {
        'total': queryset.count(),
        'pending': 0,
        'processing': 0,
        'sent': 0,
        'failed': 0,
        'cancelled': 0
    }
    
    for stat in stats:
        result[stat['status']] = stat['count']
    
    return result


def cancel_queued_sms(batch_id=None, sms_ids=None):
    """
    Cancel pending SMS in queue
    """
    from .models import SMSQueue
    
    queryset = SMSQueue.objects.filter(status='pending')
    
    if batch_id:
        queryset = queryset.filter(batch_id=batch_id)
    elif sms_ids:
        queryset = queryset.filter(id__in=sms_ids)
    else:
        return {'success': False, 'error': 'Provide batch_id or sms_ids'}
    
    count = queryset.update(status='cancelled')
    return {'success': True, 'cancelled': count}


# ============================================
# FEE-RELATED SMS FUNCTIONS
# ============================================

def send_fee_reminder_sms(student, balance, due_date, created_by=None):
    """
    Send fee reminder SMS to parents and guardians. Sends to parents first,
    then to primary guardian if no parents or parent has no phone.
    """
    from .models import SMSTemplate, Parent, Guardian
    
    school = get_school_settings()
    
    # Try to get fee reminder template
    template = SMSTemplate.objects.filter(
        template_type='fee_reminder',
        is_active=True
    ).first()
    
    if template:
        message = template.content
    else:
        message = "{school_name}: Dear {parent_name}, this is a reminder that school fees balance of KES {amount} for {student_name} is due on {date}. Please make payment to avoid inconvenience."
    
    student_name = f"{student.admin.first_name} {student.admin.last_name}"
    date_str = due_date.strftime('%d/%m/%Y') if due_date else 'N/A'
    balance_str = f"{balance:,.2f}"
    
    results = []
    sent_phones = set()
    
    # Send to parents
    parents = Parent.objects.filter(children=student)
    for parent in parents:
        context = {
            'student_name': student_name,
            'parent_name': parent.admin.first_name,
            'amount': balance_str,
            'balance': balance_str,
            'date': date_str,
            'school_name': school.school_name
        }
        personalized_msg = render_sms_template(message, context)
        phone = format_phone_number(parent.admin.phone_number) if parent.admin.phone_number else None
        if phone and phone not in sent_phones:
            result = add_to_sms_queue(
                phone_number=phone,
                message=personalized_msg,
                recipient_type='parent',
                recipient_id=parent.id,
                template=template,
                created_by=created_by
            )
            results.append(result)
            sent_phones.add(phone)
    
    # If no parents with phone, send to primary guardian
    if not sent_phones:
        primary_guardian = Guardian.objects.filter(
            student=student, is_primary=True
        ).first() or Guardian.objects.filter(student=student).first()
        if primary_guardian and primary_guardian.phone_number:
            phone = format_phone_number(primary_guardian.phone_number)
            if phone:
                context = {
                    'student_name': student_name,
                    'parent_name': primary_guardian.name,
                    'amount': balance_str,
                    'balance': balance_str,
                    'date': date_str,
                    'school_name': school.school_name
                }
                personalized_msg = render_sms_template(message, context)
                result = add_to_sms_queue(
                    phone_number=phone,
                    message=personalized_msg,
                    recipient_type='parent',
                    recipient_id=primary_guardian.id,
                    template=template,
                    created_by=created_by
                )
                results.append(result)
    
    return results


def send_payment_receipt_sms(payment, created_by=None):
    """
    Send payment receipt SMS after fee payment to student, parents, and guardians.
    """
    school = get_school_settings()
    student = payment.student
    student_name = f"{student.admin.first_name} {student.admin.last_name}"

    message = f"{school.school_name}: Payment received. Receipt No: {payment.receipt_number}. Amount: KES {payment.amount:,.2f}. Student: {student_name}. Thank you."

    sent_phones = set()

    # Send to student phone
    if student.admin.phone_number:
        phone = format_phone_number(student.admin.phone_number)
        if phone:
            add_to_sms_queue(
                phone_number=phone,
                message=message,
                recipient_type='student',
                recipient_id=student.id,
                created_by=created_by
            )
            sent_phones.add(phone)

    # Send to parents
    from .models import Parent, Guardian
    parents = Parent.objects.filter(children=student)
    parent_sent = False
    for parent in parents:
        if parent.admin.phone_number:
            phone = format_phone_number(parent.admin.phone_number)
            if phone and phone not in sent_phones:
                add_to_sms_queue(
                    phone_number=phone,
                    message=message,
                    recipient_type='parent',
                    recipient_id=parent.id,
                    created_by=created_by
                )
                sent_phones.add(phone)
                parent_sent = True

    # If no parent with phone, send to primary guardian
    if not parent_sent:
        primary_guardian = Guardian.objects.filter(
            student=student, is_primary=True
        ).first() or Guardian.objects.filter(student=student).first()
        if primary_guardian and primary_guardian.phone_number:
            phone = format_phone_number(primary_guardian.phone_number)
            if phone and phone not in sent_phones:
                add_to_sms_queue(
                    phone_number=phone,
                    message=message,
                    recipient_type='parent',
                    recipient_id=primary_guardian.id,
                    created_by=created_by
                )


# ============================================
# ATTENDANCE-RELATED SMS FUNCTIONS
# ============================================

def send_attendance_alert_sms(student, date, created_by=None):
    """
    Send SMS alert when student is marked absent
    """
    from .models import SMSTemplate, Parent
    
    school = get_school_settings()
    
    if not school.enable_attendance_sms:
        return {'success': False, 'error': 'Attendance SMS disabled'}
    
    # Try to get attendance alert template
    template = SMSTemplate.objects.filter(
        template_type='attendance_alert',
        is_active=True
    ).first()
    
    if template:
        message = template.content
    else:
        message = "{school_name}: Dear {parent_name}, your child {student_name} was marked absent on {date}. Please contact the school if this is an error."
    
    parents = Parent.objects.filter(children=student)
    
    results = []
    for parent in parents:
        context = {
            'student_name': f"{student.admin.first_name} {student.admin.last_name}",
            'parent_name': f"{parent.admin.first_name}",
            'date': date.strftime('%d/%m/%Y'),
            'class_name': str(student.course) if student.course else 'N/A',
            'school_name': school.school_name
        }
        
        personalized_msg = render_sms_template(message, context)
        
        if parent.admin.phone_number:
            result = add_to_sms_queue(
                phone_number=parent.admin.phone_number,
                message=personalized_msg,
                recipient_type='parent',
                recipient_id=parent.id,
                template=template,
                created_by=created_by
            )
            results.append(result)
    
    return results


# Import models at module level for process_sms_queue
from django.db import models


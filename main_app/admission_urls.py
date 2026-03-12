"""
URL names allowed for Admission Officer (user_type='6').
Admission Officer can ONLY access these URLs. All others return 403.
"""
ADMISSION_OFFICER_ALLOWED_URL_NAMES = frozenset([
    # Auth & assets
    'login_page',
    'user_login',
    'user_logout',
    'showFirebaseJS',
    # Admission Dashboard & Core
    'admission_dashboard',
    'admission_new_student',
    'admission_bulk',
    'admission_class_allocation',
    'admission_student_documents',
    'admission_student_documents_list',
    'admission_document_delete',
    'admission_reports',
    # Check email (for admission form)
    'check_email_availability',
    # Notifications (navbar bell)
    'notification_list',
    'mark_notification_read',
])

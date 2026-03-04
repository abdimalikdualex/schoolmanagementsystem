"""
URL names allowed for Finance Officer (user_type='5').
Finance Officer can ONLY access these URLs. All others return 403.
"""
FINANCE_OFFICER_ALLOWED_URL_NAMES = frozenset([
    # Auth & assets
    'login_page',
    'user_login',
    'user_logout',
    'showFirebaseJS',
    # Finance Dashboard & Core
    'finance_dashboard',
    'fee_collection',
    'finance_student_billing',
    'finance_defaulters',
    'finance_profile',
    # Fee Structure
    'manage_fee_types',
    'edit_fee_type',
    'manage_fee_groups',
    'edit_fee_group',
    'manage_fee_structures',
    'finance_generate_invoices',
    # Reports
    'finance_term_report',
    'finance_class_report',
    'student_fee_statement',
    'print_fee_statement',
    'print_fee_receipt',
    'send_fee_reminders',
    # Student fees (for recording payment, viewing statement)
    'student_detail_fees',
    'student_add_fee_payment',
    'student_edit_fee_payment',
    'student_delete_fee_payment',
    'student_print_fee_receipt',
    'student_print_fee_statement_detail',
    # Student detail (to reach fees tab - read-only)
    'student_detail',
])

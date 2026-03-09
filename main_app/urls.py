"""school_management_system URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path

from main_app.EditResultView import EditResultView

from . import hod_views, staff_views, student_views, parent_views, views, finance_views, super_admin_views, report_card_views

urlpatterns = [
    path("", views.login_page, name='login_page'),
    path("login/", views.login_page),
    path("register/school/", views.school_registration, name='school_registration'),
    path("verify-email/<str:token>/", views.verify_email, name='verify_email'),
    path("get_attendance", views.get_attendance, name='get_attendance'),
    path("firebase-messaging-sw.js", views.showFirebaseJS, name='showFirebaseJS'),
    path("doLogin/", views.doLogin, name='user_login'),
    path("logout_user/", views.logout_user, name='user_logout'),
    path("notifications/", views.notification_list, name='notification_list'),
    path("notifications/<int:notification_id>/read/", views.mark_notification_read, name='mark_notification_read'),
    path("superadmin/dashboard/", super_admin_views.super_admin_dashboard, name='super_admin_dashboard'),
    path("superadmin/school/create/", super_admin_views.super_admin_create_school, name='super_admin_create_school'),
    path("superadmin/school/<int:school_id>/edit/", super_admin_views.super_admin_edit_school, name='super_admin_edit_school'),
    path("superadmin/school/<int:school_id>/approve/", super_admin_views.super_admin_approve_school, name='super_admin_approve_school'),
    path("superadmin/school/<int:school_id>/reject/", super_admin_views.super_admin_reject_school, name='super_admin_reject_school'),
    path("superadmin/school/<int:school_id>/suspend/", super_admin_views.super_admin_suspend_school, name='super_admin_suspend_school'),
    path("superadmin/school/<int:school_id>/deactivate/", super_admin_views.super_admin_deactivate_school, name='super_admin_deactivate_school'),
    path("superadmin/school/<int:school_id>/delete/", super_admin_views.super_admin_delete_school, name='super_admin_delete_school'),
    path("superadmin/school/<int:school_id>/view/", super_admin_views.super_admin_view_school, name='super_admin_view_school'),
    path("superadmin/users/<int:user_id>/reset-password/", super_admin_views.super_admin_reset_password, name='super_admin_reset_password'),
    path("superadmin/users/", super_admin_views.super_admin_user_monitoring, name='super_admin_user_monitoring'),
    path("superadmin/plans/", super_admin_views.super_admin_manage_plans, name='super_admin_manage_plans'),
    path("superadmin/plans/create/", super_admin_views.super_admin_create_plan, name='super_admin_create_plan'),
    path("superadmin/plans/<int:plan_id>/edit/", super_admin_views.super_admin_edit_plan, name='super_admin_edit_plan'),
    path("admin/home/", hod_views.admin_home, name='admin_home'),
    path("staff/add", hod_views.add_staff, name='add_staff'),
    path("class/add", hod_views.add_class, name='add_course'),  # Legacy name for compatibility
    path("send_student_notification/", hod_views.send_student_notification,
         name='send_student_notification'),
    path("send_staff_notification/", hod_views.send_staff_notification,
         name='send_staff_notification'),
    path("add_session/", hod_views.add_session, name='add_session'),
    path("admin_notify_student", hod_views.admin_notify_student,
         name='admin_notify_student'),
    path("admin_notify_staff", hod_views.admin_notify_staff,
         name='admin_notify_staff'),
    path("admin_view_profile", hod_views.admin_view_profile,
         name='admin_view_profile'),
    path("check_email_availability", hod_views.check_email_availability,
         name="check_email_availability"),
    path("session/manage/", hod_views.manage_session, name='manage_session'),
    path("session/edit/<int:session_id>",
         hod_views.edit_session, name='edit_session'),
    path("student/view/feedback/", hod_views.student_feedback_message,
         name="student_feedback_message",),
    path("staff/view/feedback/", hod_views.staff_feedback_message,
         name="staff_feedback_message",),
    path("student/view/leave/", hod_views.view_student_leave,
         name="view_student_leave",),
    path("staff/view/leave/", hod_views.view_staff_leave, name="view_staff_leave",),
    path("attendance/view/", hod_views.admin_view_attendance,
         name="admin_view_attendance",),
    path("attendance/fetch/", hod_views.get_admin_attendance,
         name='get_admin_attendance'),
    path("result/view/", hod_views.admin_view_result,
         name='admin_view_result'),
    path("result/edit/", hod_views.admin_edit_result,
         name='admin_edit_result'),
    path("result/fetch/", hod_views.admin_fetch_student_result,
         name='admin_fetch_student_result'),
    path("result/get_students/", hod_views.admin_get_students_for_result,
         name='admin_get_students_for_result'),
    path("result/superadmin/search/", hod_views.superadmin_search_student_results, name='superadmin_search_results'),
    path("result/superadmin/update/", hod_views.superadmin_update_student_result, name='superadmin_update_result'),
    path("transcript/view/", hod_views.admin_view_transcript,
         name='admin_view_transcript'),
    path("transcript/get/", hod_views.admin_get_student_transcript,
         name='admin_get_student_transcript'),
    path("transcript/download/<int:student_id>/", hod_views.admin_download_transcript_pdf,
         name='admin_download_transcript_pdf'),
    path("transcript/send-sms/<int:student_id>/", hod_views.send_results_sms,
         name='send_results_sms'),
    path("transcript/send-sms-all/", hod_views.send_all_results_sms,
         name='send_all_results_sms'),
     path("admission/config/", hod_views.admission_setting_view, name='admission_setting'),
     path("student/search/", hod_views.student_search, name='student_search'),
     path("student/profile/<int:student_id>/", hod_views.student_profile, name='student_profile'),
    path("fees/view/", hod_views.admin_view_fees,
         name='admin_view_fees'),
    path("fees/post/", hod_views.admin_post_fees,
         name='admin_post_fees'),
    path("fees/get/", hod_views.admin_get_fees,
         name='admin_get_fees'),
    path("fees/clear/", hod_views.admin_clear_fees,
         name='admin_clear_fees'),
    path("permissions/manage/", hod_views.admin_manage_permissions,
         name='admin_manage_permissions'),
    path("permissions/update/", hod_views.admin_update_permission,
         name='admin_update_permission'),
    path("student/add/", hod_views.add_student, name='add_student'),
    path("subject/add/", hod_views.add_subject, name='add_subject'),
    path("staff/manage/", hod_views.manage_staff, name='manage_staff'),
    path("student/manage/", hod_views.manage_student, name='manage_student'),
    path("class/manage/", hod_views.manage_classes, name='manage_course'),  # Legacy name for compatibility
    path("subject/manage/", hod_views.manage_subject, name='manage_subject'),
    path("staff/edit/<int:staff_id>", hod_views.edit_staff, name='edit_staff'),
    path("staff/delete/<int:staff_id>",
         hod_views.delete_staff, name='delete_staff'),

    path("class/delete/<int:course_id>",
         hod_views.delete_class, name='delete_course'),  # Legacy name for compatibility

    path("subject/delete/<int:subject_id>",
         hod_views.delete_subject, name='delete_subject'),

    path("session/delete/<int:session_id>",
         hod_views.delete_session, name='delete_session'),

    # Academic Terms
    path("academic-terms/", hod_views.manage_academic_terms, name='manage_academic_terms'),
    path("academic-terms/add/", hod_views.add_academic_term, name='add_academic_term'),
    path("academic-terms/edit/<int:term_id>/", hod_views.edit_academic_term, name='edit_academic_term'),
    path("academic-terms/activate/<int:term_id>/", hod_views.activate_academic_term, name='activate_academic_term'),
    path("academic-terms/close/<int:term_id>/", hod_views.close_academic_term, name='close_academic_term'),
    path("academic-terms/delete/<int:term_id>/", hod_views.delete_academic_term, name='delete_academic_term'),

    path("student/delete/<int:student_id>",
         hod_views.delete_student, name='delete_student'),
    path("student/edit/<int:student_id>",
         hod_views.edit_student, name='edit_student'),
    path("class/edit/<int:course_id>",
         hod_views.edit_class, name='edit_course'),  # Legacy name for compatibility
    path("subject/edit/<int:subject_id>",
         hod_views.edit_subject, name='edit_subject'),


    # Staff
    path("staff/home/", staff_views.staff_home, name='staff_home'),
    path("staff/apply/leave/", staff_views.staff_apply_leave,
         name='staff_apply_leave'),
    path("staff/feedback/", staff_views.staff_feedback, name='staff_feedback'),
    path("staff/view/profile/", staff_views.staff_view_profile,
         name='staff_view_profile'),
    path("staff/attendance/take/", staff_views.staff_take_attendance,
         name='staff_take_attendance'),
    path("staff/attendance/update/", staff_views.staff_update_attendance,
         name='staff_update_attendance'),
    path("staff/get_students/", staff_views.get_students, name='get_students'),
    path("staff/attendance/fetch/", staff_views.get_student_attendance,
         name='get_student_attendance'),
    path("staff/attendance/save/",
         staff_views.save_attendance, name='save_attendance'),
    path("staff/attendance/update/",
         staff_views.update_attendance, name='update_attendance'),
    path("staff/fcmtoken/", staff_views.staff_fcmtoken, name='staff_fcmtoken'),
    path("staff/view/notification/", staff_views.staff_view_notification,
         name="staff_view_notification"),
    path("staff/result/add/", staff_views.staff_add_result, name='staff_add_result'),
    path("staff/result/edit/", EditResultView.as_view(),
         name='edit_student_result'),
    path('staff/result/fetch/', staff_views.fetch_student_result,
         name='fetch_student_result'),



    # Student
    path("student/home/", student_views.student_home, name='student_home'),
    path("student/view/attendance/", student_views.student_view_attendance,
         name='student_view_attendance'),
    path("student/apply/leave/", student_views.student_apply_leave,
         name='student_apply_leave'),
    path("student/feedback/", student_views.student_feedback,
         name='student_feedback'),
    path("student/view/profile/", student_views.student_view_profile,
         name='student_view_profile'),
    path("student/fcmtoken/", student_views.student_fcmtoken,
         name='student_fcmtoken'),
    path("student/view/notification/", student_views.student_view_notification,
         name="student_view_notification"),
    path('student/view/result/', student_views.student_view_result,
         name='student_view_result'),
    path('student/view/fees/', student_views.student_view_fees,
         name='student_view_fees'),
    path('student/view/timetable/', student_views.student_view_timetable,
         name='student_view_timetable'),
    path('student/view/homework/', student_views.student_view_homework,
         name='student_view_homework'),
    path('student/submit/homework/<int:homework_id>/', student_views.student_submit_homework,
         name='student_submit_homework'),
    path('student/view/announcements/', student_views.student_view_announcements,
         name='student_view_announcements'),

    # Parent URLs
    path("parent/home/", parent_views.parent_home, name='parent_home'),
    path("parent/children/", parent_views.parent_view_children, name='parent_view_children'),
    path("parent/attendance/", parent_views.parent_view_attendance, name='parent_view_attendance'),
    path("parent/results/", parent_views.parent_view_results, name='parent_view_results'),
    path("parent/child/<int:student_id>/", parent_views.parent_view_child_profile, name='parent_view_child_profile'),
    path("parent/child/<int:student_id>/report-card/", parent_views.parent_view_report_card, name='parent_view_report_card'),
    path("parent/child/<int:student_id>/report-card/<int:term_id>/", parent_views.parent_view_knec_report_card, name='parent_view_knec_report_card'),
    path("parent/child/<int:student_id>/report-card/<int:term_id>/download/", parent_views.parent_download_knec_report_card_pdf, name='parent_download_knec_report_card_pdf'),
    path("parent/child/<int:student_id>/report-card/download/", parent_views.parent_download_report_card_pdf, name='parent_download_report_card_pdf'),
    path("parent/child/<int:student_id>/attendance/", parent_views.parent_view_child_attendance,
         name='parent_view_child_attendance'),
    path("parent/child/<int:student_id>/results/", parent_views.parent_view_child_results,
         name='parent_view_child_results'),
    path("parent/child/<int:student_id>/fees/", parent_views.parent_view_child_fees,
         name='parent_view_child_fees'),
    path("parent/child/<int:student_id>/timetable/", parent_views.parent_view_child_timetable,
         name='parent_view_child_timetable'),
    path("parent/child/<int:student_id>/homework/", parent_views.parent_view_child_homework,
         name='parent_view_child_homework'),
    path("parent/announcements/", parent_views.parent_view_announcements,
         name='parent_view_announcements'),
    path("parent/messages/", parent_views.parent_view_messages,
         name='parent_view_messages'),
    path("parent/messages/send/", parent_views.parent_send_message,
         name='parent_send_message'),
    path("parent/messages/mark-read/", parent_views.parent_mark_message_read,
         name='parent_mark_message_read'),
    path("parent/profile/", parent_views.parent_view_profile,
         name='parent_view_profile'),
    path("parent/notifications/", parent_views.parent_view_notifications,
         name='parent_view_notifications'),
    path("parent/fcmtoken/", parent_views.parent_fcmtoken,
         name='parent_fcmtoken'),

    # Admin - Section Management
    path("section/add/", hod_views.add_section, name='add_section'),
    path("section/manage/", hod_views.manage_section, name='manage_section'),
    path("section/edit/<int:section_id>/", hod_views.edit_section, name='edit_section'),
    path("section/delete/<int:section_id>/", hod_views.delete_section, name='delete_section'),

    # Admin - Parent Management
    path("parent/add/", hod_views.add_parent, name='add_parent'),
    path("parent/manage/", hod_views.manage_parent, name='manage_parent'),
    path("parent/edit/<int:parent_id>/", hod_views.edit_parent, name='edit_parent'),
    path("parent/delete/<int:parent_id>/", hod_views.delete_parent, name='delete_parent'),
    path("parent/link-child/", hod_views.link_parent_child, name='link_parent_child'),

    # Admin - Timetable Management
    path("timetable/add/", hod_views.add_timetable, name='add_timetable'),
    path("timetable/manage/", hod_views.manage_timetable, name='manage_timetable'),
    path("timetable/edit/<int:timetable_id>/", hod_views.edit_timetable, name='edit_timetable'),
    path("timetable/delete/<int:timetable_id>/", hod_views.delete_timetable, name='delete_timetable'),
    path("timetable/view/<int:class_id>/", hod_views.view_class_timetable, name='view_class_timetable'),

    # Admin - Announcements
    path("announcement/add/", hod_views.add_announcement, name='add_announcement'),
    path("announcement/manage/", hod_views.manage_announcement, name='manage_announcement'),
    path("announcement/edit/<int:announcement_id>/", hod_views.edit_announcement, name='edit_announcement'),
    path("announcement/delete/<int:announcement_id>/", hod_views.delete_announcement, name='delete_announcement'),

    # Staff - Homework Management
    path("staff/homework/add/", staff_views.staff_add_homework, name='staff_add_homework'),
    path("staff/homework/manage/", staff_views.staff_manage_homework, name='staff_manage_homework'),
    path("staff/homework/edit/<int:homework_id>/", staff_views.staff_edit_homework, name='staff_edit_homework'),
    path("staff/homework/delete/<int:homework_id>/", staff_views.staff_delete_homework, name='staff_delete_homework'),
    path("staff/homework/submissions/<int:homework_id>/", staff_views.staff_view_submissions, name='staff_view_submissions'),
    path("staff/homework/grade/<int:submission_id>/", staff_views.staff_grade_submission, name='staff_grade_submission'),
    path("staff/timetable/", staff_views.staff_view_timetable, name='staff_view_timetable'),
    path("staff/messages/", staff_views.staff_view_messages, name='staff_view_messages'),
    path("staff/messages/send/", staff_views.staff_send_message, name='staff_send_message'),
    path("staff/messages/reply/<int:message_id>/", staff_views.staff_reply_message, name='staff_reply_message'),

    # ============================================================
    # KENYA CBC CLASS MANAGEMENT
    # ============================================================
    
    # Grade Level Management
    path("grade-levels/", hod_views.manage_grade_levels, name='manage_grade_levels'),
    path("grade-levels/add/", hod_views.add_grade_level, name='add_grade_level'),
    path("grade-levels/edit/<int:grade_level_id>/", hod_views.edit_grade_level, name='edit_grade_level'),
    path("grade-levels/delete/<int:grade_level_id>/", hod_views.delete_grade_level, name='delete_grade_level'),
    
    # Stream Management
    path("streams/", hod_views.manage_streams, name='manage_streams'),
    path("streams/add/", hod_views.add_stream, name='add_stream'),
    path("streams/edit/<int:stream_id>/", hod_views.edit_stream, name='edit_stream'),
    path("streams/delete/<int:stream_id>/", hod_views.delete_stream, name='delete_stream'),
    
    # Class Management
    path("classes/", hod_views.manage_classes, name='manage_classes'),
    path("classes/add/", hod_views.add_class, name='add_class'),
    path("classes/edit/<int:class_id>/", hod_views.edit_class, name='edit_class'),
    path("classes/delete/<int:class_id>/", hod_views.delete_class, name='delete_class'),
    path("classes/<int:class_id>/students/", hod_views.view_class_students, name='view_class_students'),
    
    # Student Enrollment Management
    path("enrollments/", hod_views.manage_enrollments, name='manage_enrollments'),
    path("enrollments/add/", hod_views.add_enrollment, name='add_enrollment'),
    path("enrollments/bulk/", hod_views.bulk_enrollment, name='bulk_enrollment'),
    path("enrollments/transfer/<int:enrollment_id>/", hod_views.transfer_student, name='transfer_student'),
    
    # Student Promotion
    path("promotions/", hod_views.promotion_dashboard, name='promotion_dashboard'),
    path("promotions/bulk/", hod_views.bulk_promote, name='bulk_promote'),
    path("promotions/history/", hod_views.promotion_history, name='promotion_history'),
    
    # AJAX endpoints for class management
    path("api/class-students/", hod_views.get_class_students, name='get_class_students'),
    path("api/next-grade-class/", hod_views.get_next_grade_class, name='get_next_grade_class'),
    
    # Staff - Class Views
    path("staff/my-class/", staff_views.staff_view_my_class, name='staff_view_my_class'),
    path("staff/class/<int:class_id>/roster/", staff_views.staff_view_class_roster, name='staff_view_class_roster'),
    
    # Student - Class Info
    path("student/class/info/", student_views.student_view_class_info, name='student_view_class_info'),
    path("student/class/classmates/", student_views.student_view_classmates, name='student_view_classmates'),
    
    # Parent - Class Info
    path("parent/child/<int:student_id>/class/", parent_views.parent_view_child_class, name='parent_view_child_class'),

    # ============================================================
    # BULK SMS MANAGEMENT
    # ============================================================
    path("sms/bulk/", hod_views.bulk_sms, name='bulk_sms'),
    path("sms/templates/", hod_views.sms_templates, name='sms_templates'),
    path("sms/templates/edit/<int:template_id>/", hod_views.edit_sms_template, name='edit_sms_template'),
    path("sms/templates/delete/<int:template_id>/", hod_views.delete_sms_template, name='delete_sms_template'),
    path("sms/reports/", hod_views.sms_reports, name='sms_reports'),
    path("sms/process-queue/", hod_views.process_sms_queue_view, name='process_sms_queue'),

    # ============================================================
    # FEE STRUCTURE MANAGEMENT
    # ============================================================
    path("fees/types/", hod_views.manage_fee_types, name='manage_fee_types'),
    path("fees/types/edit/<int:fee_type_id>/", hod_views.edit_fee_type, name='edit_fee_type'),
    path("fees/groups/", hod_views.manage_fee_groups, name='manage_fee_groups'),
    path("fees/groups/edit/<int:group_id>/", hod_views.edit_fee_group, name='edit_fee_group'),
    path("fees/structures/", hod_views.manage_fee_structures, name='manage_fee_structures'),
    path("fees/dashboard/", hod_views.finance_dashboard, name='finance_dashboard'),
    path("finance/officers/add/", hod_views.add_finance_officer, name='add_finance_officer'),
    path("finance/officers/manage/", hod_views.manage_finance_officers, name='manage_finance_officers'),
    path("finance/profile/", finance_views.finance_profile, name='finance_profile'),
    path("finance/students/billing/", finance_views.finance_student_billing, name='finance_student_billing'),
    path("finance/defaulters/", finance_views.finance_defaulters, name='finance_defaulters'),
    path("fees/reports/term/", hod_views.finance_term_report, name='finance_term_report'),
    path("fees/reports/class/", hod_views.finance_class_report, name='finance_class_report'),
    path("fees/generate-invoices/", hod_views.finance_generate_invoices, name='finance_generate_invoices'),
    path("fees/collection/", hod_views.fee_collection, name='fee_collection'),
    path("fees/statement/<int:student_id>/", hod_views.student_fee_statement, name='student_fee_statement'),
    path("fees/receipt/print/<int:payment_id>/", hod_views.print_fee_receipt, name='print_fee_receipt'),
    path("fees/statement/print/<int:student_id>/", hod_views.print_fee_statement, name='print_fee_statement'),
    path("fees/reminders/send/", hod_views.send_fee_reminders, name='send_fee_reminders'),

    # ============================================================
    # EXAM & RESULT MANAGEMENT
    # ============================================================
    path("exams/types/", hod_views.manage_exam_types, name='manage_exam_types'),
    path("exams/schedules/", hod_views.manage_exam_schedules, name='manage_exam_schedules'),
    path("exams/result-entry/", hod_views.manage_result_entry, name='manage_result_entry'),
    path("exams/grading-scale/", hod_views.manage_grading_scale, name='manage_grading_scale'),
    path("exams/results/enter/", hod_views.enter_exam_results, name='enter_exam_results'),
    path("exams/results/submit/", hod_views.teacher_submit_results, name='teacher_submit_results'),
    path("exams/results/status/", hod_views.result_submission_status, name='result_submission_status'),
    path("exams/results/publish/", hod_views.publish_term_results, name='publish_term_results'),
    path("exams/results/unpublish/", hod_views.unpublish_term_results, name='unpublish_term_results'),
    path("exams/results/unlock/", hod_views.admin_unlock_teacher_submission, name='admin_unlock_teacher_submission'),
    path("exams/cats/enter/", hod_views.enter_cat_marks, name='enter_cat_marks'),
    path("exams/results/view/", hod_views.view_exam_results, name='view_exam_results'),
    path("exams/results/slip/<int:student_id>/<int:exam_schedule_id>/", hod_views.print_result_slip, name='print_result_slip'),
    path("exams/results/bulk-print/", hod_views.bulk_print_result_slips, name='bulk_print_result_slips'),
    path("api/students-for-results/", hod_views.get_students_for_results, name='get_students_for_results'),

    # ============================================================
    # KNEC REPORT CARDS
    # ============================================================
    path("report-cards/", report_card_views.report_card_list, name='report_card_list'),
    path("report-cards/enter-marks/", report_card_views.knec_enter_marks, name='knec_enter_marks'),
    path("report-cards/view/<int:student_id>/<int:term_id>/", report_card_views.report_card_view, name='report_card_view'),
    path("report-cards/pdf/<int:student_id>/<int:term_id>/", report_card_views.report_card_pdf, name='report_card_pdf'),

    # ============================================================
    # CLASS ATTENDANCE MANAGEMENT
    # ============================================================
    path("attendance/dashboard/", hod_views.attendance_dashboard, name='attendance_dashboard'),
    path("attendance/take/", hod_views.take_class_attendance, name='take_class_attendance'),
    path("attendance/class/<int:class_id>/", hod_views.view_class_attendance, name='view_class_attendance'),
    path("attendance/student/<int:student_id>/", hod_views.student_attendance_report, name='student_attendance_report'),
    path("api/students-for-attendance/", hod_views.get_class_students_for_attendance, name='get_class_students_for_attendance'),

    # ============================================================
    # SCHOOL SETTINGS
    # ============================================================
    path("settings/school/", hod_views.school_settings, name='school_settings'),

    # ============================================================
    # STUDENT DETAIL PAGE (with tabs: General, Fee Payment, Exam Results, SMS Messages)
    # ============================================================
    path("students/detail/<int:student_id>/", hod_views.student_detail, name='student_detail'),
    path("students/detail/<int:student_id>/general/", hod_views.student_detail_general, name='student_detail_general'),
    path("students/detail/<int:student_id>/fees/", hod_views.student_detail_fees, name='student_detail_fees'),
    path("students/detail/<int:student_id>/fees/add/", hod_views.student_add_fee_payment, name='student_add_fee_payment'),
    path("students/detail/<int:student_id>/fees/edit/<int:payment_id>/", hod_views.student_edit_fee_payment, name='student_edit_fee_payment'),
    path("students/detail/<int:student_id>/fees/delete/<int:payment_id>/", hod_views.student_delete_fee_payment, name='student_delete_fee_payment'),
    path("students/detail/<int:student_id>/fees/print/<int:payment_id>/", hod_views.student_print_fee_receipt, name='student_print_fee_receipt'),
    path("students/detail/<int:student_id>/fees/statement/", hod_views.student_print_fee_statement, name='student_print_fee_statement_detail'),
    path("students/detail/<int:student_id>/results/", hod_views.student_detail_results, name='student_detail_results'),
    path("students/detail/<int:student_id>/results/add/", hod_views.student_add_result, name='student_add_result'),
    path("students/detail/<int:student_id>/results/edit/<int:result_id>/", hod_views.student_edit_result, name='student_edit_result'),
    path("students/detail/<int:student_id>/results/delete/<int:result_id>/", hod_views.student_delete_result, name='student_delete_result'),
    path("students/detail/<int:student_id>/sms/", hod_views.student_detail_sms, name='student_detail_sms'),
    path("students/detail/<int:student_id>/sms/send/", hod_views.student_send_sms, name='student_send_sms'),
    
    # Guardian management
    path("students/detail/<int:student_id>/guardian/add/", hod_views.student_add_guardian, name='student_add_guardian'),
    path("students/detail/<int:student_id>/guardian/edit/<int:guardian_id>/", hod_views.student_edit_guardian, name='student_edit_guardian'),
    path("students/detail/<int:student_id>/guardian/delete/<int:guardian_id>/", hod_views.student_delete_guardian, name='student_delete_guardian'),

]

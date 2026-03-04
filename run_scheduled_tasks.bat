@echo off
REM School Management System - Scheduled Tasks Runner
REM Add this batch file to Windows Task Scheduler to automate school operations
REM 
REM Recommended Schedule:
REM - process_sms_queue: Every 5 minutes
REM - send_fee_reminders: Daily at 9:00 AM
REM - send_attendance_alerts: Daily at 12:00 PM
REM - generate_fee_statements: 1st of each month

cd /d "%~dp0"

REM Activate virtual environment if using one
REM call venv\Scripts\activate

echo [%date% %time%] Starting scheduled tasks...

REM Process SMS Queue
echo Processing SMS queue...
python manage.py process_sms_queue --batch-size=100

REM Send Fee Reminders (only run once daily)
if "%1"=="daily" (
    echo Sending fee reminders...
    python manage.py send_fee_reminders
)

REM Send Attendance Alerts (only run once daily)
if "%1"=="daily" (
    echo Sending attendance alerts...
    python manage.py send_attendance_alerts
)

REM Generate Fee Statements (only run monthly)
if "%1"=="monthly" (
    echo Generating fee statements...
    python manage.py generate_fee_statements --send-sms
)

echo [%date% %time%] Scheduled tasks completed.

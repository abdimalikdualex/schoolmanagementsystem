"""
Email service for school registration: verification and approval notifications.
Uses Django's email backend. Configure EMAIL_* in settings for production (SendGrid, Mailgun, etc.).
"""
import logging
import secrets
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _is_real_email_backend():
    """Check if we're using a backend that actually delivers email (not console/file)."""
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    return backend and 'console' not in backend and 'file' not in backend


def get_from_email():
    """Default from address for system emails."""
    return getattr(settings, 'DEFAULT_FROM_EMAIL', settings.EMAIL_HOST_USER or 'noreply@schoolsystem.com')


def send_verification_email(user, verification_url):
    """Send email verification link to new school admin."""
    subject = "Verify your school admin email"
    html_message = f"""
    <p>Hello {user.first_name},</p>
    <p>Please verify your email to activate your school account.</p>
    <p>Click the link below:</p>
    <p><a href="{verification_url}" style="background:#28a745;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;">Verify Email</a></p>
    <p>Or copy this link: {verification_url}</p>
    <p>Thank you.</p>
    """
    plain_message = strip_tags(html_message)
    try:
        sent = send_mail(
            subject=subject,
            message=plain_message,
            from_email=get_from_email(),
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )
        return sent > 0
    except Exception:
        return False


def send_school_approval_email(school, admin_email, login_url):
    """Send approval notification when platform owner approves a school.
    Returns True if email was actually sent; False if not (console backend, config missing, or error).
    """
    if not _is_real_email_backend():
        logger.warning(
            "Approval email not sent: using console/file backend. "
            "Set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in environment for real delivery."
        )
        return False

    subject = "Your School Has Been Approved"
    html_message = f"""
    <p>Hello,</p>
    <p>Your school <strong>{school.name}</strong> has been approved on our platform.</p>
    <p>You can now log in and start using the system.</p>
    <p><a href="{login_url}" style="background:#007bff;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;">Log In</a></p>
    <p>Login URL: {login_url}</p>
    <p>Thank you.</p>
    """
    plain_message = strip_tags(html_message)
    try:
        sent = send_mail(
            subject=subject,
            message=plain_message,
            from_email=get_from_email(),
            recipient_list=[admin_email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent == 0:
            logger.warning("Approval email returned 0 sent for %s", admin_email)
            return False
        return True
    except Exception as e:
        logger.exception("Failed to send approval email to %s: %s", admin_email, e)
        return False


def generate_verification_token():
    """Generate a secure random token for email verification."""
    return secrets.token_urlsafe(32)

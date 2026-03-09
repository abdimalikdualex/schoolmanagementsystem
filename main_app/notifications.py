"""
MVP Notification helper - create notifications from anywhere in the system.
"""
from .models import Notification


def create_notification(user, title, message, link=None, school=None):
    """
    Create an in-app notification for a user.
    Call from views when events occur (results submitted, fee paid, etc.).

    Args:
        user: CustomUser recipient
        title: Short title (e.g. "Results Submitted")
        message: Body text (e.g. "Teacher John submitted Grade 4 Math results")
        link: Optional URL to navigate when clicked (e.g. "/admin/exams/results/status/")
        school: Optional School for multi-tenant context
    """
    Notification.objects.create(
        recipient=user,
        title=title,
        message=message,
        link=link or "",
        school=school,
    )

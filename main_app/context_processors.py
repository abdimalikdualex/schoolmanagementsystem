"""
Context processors for templates.
"""
from django.db.models import Q

from .models import Notification


def notification_context(request):
    """
    Add notifications and unread count to every template for authenticated users.
    Used by navbar bell icon.
    """
    if request.user.is_authenticated:
        school = getattr(request, 'school', None)
        qs = Notification.objects.filter(recipient=request.user)
        if school:
            qs = qs.filter(Q(school=school) | Q(school__isnull=True))
        else:
            qs = qs.filter(school__isnull=True)

        notifications = qs.order_by("-created_at")[:10]
        unread_count = qs.filter(is_read=False).count()

        return {
            "notifications": notifications,
            "unread_notifications_count": unread_count,
        }
    return {}

from .models import Notification


def portal_context(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    return {
        "unread_notification_count": Notification.objects.filter(
            recipient=request.user, read=False
        ).count()
    }

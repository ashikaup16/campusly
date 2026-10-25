from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def roles_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles and not request.user.is_superuser:
                messages.error(request, "You don’t have permission to do that.")
                return redirect("dashboard")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def can_manage_club(user, club):
    return (
        user.is_superuser
        or user.role == "admin"
        or club.administrators.filter(pk=user.pk).exists()
        or club.coordinators.filter(pk=user.pk).exists()
    )


def can_administer_club(user, club):
    return (
        user.is_superuser
        or user.role == "admin"
        or club.administrators.filter(pk=user.pk).exists()
    )

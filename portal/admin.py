from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Club, Event, MembershipApplication, Notification, Registration, User


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Campus profile", {"fields": ("role", "department")}),)
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "starts_at", "venue", "organizer", "published")
    list_filter = ("category", "published")
    search_fields = ("title", "venue")


admin.site.register(Club)
admin.site.register(Registration)
admin.site.register(Notification)
admin.site.register(MembershipApplication)

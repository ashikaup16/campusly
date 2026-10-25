from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("events/", views.event_list, name="event_list"),
    path("clubs/<int:club_id>/events/create/", views.event_create, name="event_create"),
    path("events/<int:event_id>/edit/", views.event_edit, name="event_edit"),
    path("events/<int:event_id>/delete/", views.event_delete, name="event_delete"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/register/", views.register_event, name="register_event"),
    path("events/<int:event_id>/cancel/", views.cancel_registration, name="cancel_registration"),
    path("events/<int:event_id>/attendees/", views.attendees, name="attendees"),
    path("clubs/", views.club_list, name="club_list"),
    path("clubs/create/", views.club_create, name="club_create"),
    path("clubs/<int:club_id>/", views.club_detail, name="club_detail"),
    path("clubs/<int:club_id>/edit/", views.club_edit, name="club_edit"),
    path("clubs/<int:club_id>/apply/", views.apply_to_club, name="apply_to_club"),
    path("clubs/<int:club_id>/applications/", views.applications, name="applications"),
    path("applications/<int:application_id>/<str:decision>/", views.review_application, name="review_application"),
    path("people/", views.people, name="people"),
    path("people/create/", views.create_account, name="create_account"),
    path("people/<int:user_id>/role/", views.update_role, name="update_role"),
    path("reports/", views.reports, name="reports"),
    path("reports/download/", views.download_report, name="download_report"),
    path("notifications/", views.notifications, name="notifications"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", views.signup, name="signup"),
]

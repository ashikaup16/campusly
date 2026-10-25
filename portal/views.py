import csv
import logging
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import can_administer_club, can_manage_club, roles_required
from .event_emails import send_event_email
from .forms import (
    ClubApplicationForm,
    ClubForm,
    CreateAccountForm,
    EventForm,
    AccountRoleForm,
    SignUpForm,
)
from .models import Club, Event, MembershipApplication, Notification, Registration, User

logger = logging.getLogger(__name__)


def notify_club_members(request, event, changed=False):
    user_ids = set(
        event.club.members.filter(is_active=True).values_list("pk", flat=True)
    )
    user_ids.update(
        event.registrations.filter(status=Registration.Status.REGISTERED).values_list(
            "student_id", flat=True
        )
    )
    user_ids.discard(request.user.pk)
    recipients = list(
        User.objects.filter(pk__in=user_ids, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    kind = "updated" if changed else "announcement"
    return sum(send_event_email(event, recipient, kind) for recipient in recipients)


def home(request):
    administrator_exists = User.objects.filter(
        Q(role=User.Role.ADMIN) | Q(is_superuser=True)
    ).exists()
    return render(
        request,
        "landing.html",
        {"administrator_exists": administrator_exists},
    )


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect("login")
    user = request.user
    now = timezone.now()
    if user.role == User.Role.STUDENT:
        events = Event.objects.filter(
            published=True, starts_at__gte=now
        ).select_related("club", "organizer")
        applications = user.club_applications.select_related("club")
        my_registrations = Registration.objects.filter(
            student=user, status=Registration.Status.REGISTERED
        ).select_related("event")
        managed_clubs = Club.objects.none()
    else:
        managed_clubs = (
            Club.objects.all()
            if user.is_superuser or user.role == User.Role.ADMIN
            else user.administered_clubs.all() | user.coordinated_clubs.all()
        ).distinct()
        events = Event.objects.filter(club__in=managed_clubs).select_related(
            "club", "organizer"
        )
        if user.role != User.Role.ADMIN and not user.is_superuser:
            events = events.filter(starts_at__gte=now)
        my_registrations = Registration.objects.none()
        applications = MembershipApplication.objects.filter(
            club__in=managed_clubs, status=MembershipApplication.Status.PENDING
        ).select_related("club", "student")

    stats = {
        "events": events.count(),
        "clubs": managed_clubs.count(),
        "students": User.objects.filter(role=User.Role.STUDENT, is_active=True).count()
        if user.role == User.Role.ADMIN or user.is_superuser
        else sum(club.members.count() for club in managed_clubs),
        "registrations": Registration.objects.filter(
            event__club__in=managed_clubs,
            status=Registration.Status.REGISTERED,
        ).count(),
        "applications": applications.count(),
    }
    event_count = events.count()
    return render(
        request,
        "dashboard.html",
        {
            "events": events[:6],
            "managed_events": events if user.role != User.Role.STUDENT else events[:6],
            "event_count": event_count,
            "my_registrations": my_registrations[:4],
            "my_clubs": user.joined_clubs.all()[:6]
            if user.role == User.Role.STUDENT
            else managed_clubs[:6],
            "applications": applications[:6],
            "stats": stats,
            "greeting_name": user.first_name or user.username,
        },
    )


def event_list(request):
    events = Event.objects.filter(published=True).select_related("club", "organizer", "club")
    category = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()
    timeframe = request.GET.get("time", "upcoming")
    if category:
        events = events.filter(category=category)
    if query:
        events = events.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(venue__icontains=query)
            | Q(club__name__icontains=query)
        )
    if timeframe == "upcoming":
        events = events.filter(starts_at__gte=timezone.now())
    elif timeframe == "past":
        events = events.filter(starts_at__lt=timezone.now())
    return render(
        request,
        "events.html",
        {
            "events": events,
            "categories": Event.Category.choices,
            "selected_category": category,
            "query": query,
            "timeframe": timeframe,
        },
    )


def event_detail(request, event_id):
    event = get_object_or_404(
        Event.objects.select_related("club", "organizer"), pk=event_id
    )
    can_manage = request.user.is_authenticated and can_manage_club(
        request.user, event.club
    )
    if not event.published and not can_manage:
        raise Http404
    registration = None
    if request.user.is_authenticated:
        registration = Registration.objects.filter(event=event, student=request.user).first()
    return render(
        request,
        "event_detail.html",
        {
            "event": event,
            "registration": registration,
            "can_manage": can_manage,
        },
    )


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def event_create(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    if not can_manage_club(request.user, club):
        messages.error(request, "You do not manage this club.")
        return redirect("dashboard")
    form = EventForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        event = form.save(commit=False)
        event.club = club
        event.organizer = request.user
        event.save()
        if event.published:
            try:
                sent = notify_club_members(request, event)
                if sent:
                    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
                        messages.warning(
                            request,
                            f"Email content for {sent} club member(s) was printed to the server terminal, not delivered. Configure SMTP to send it.",
                        )
                    else:
                        messages.info(request, f"Email update sent to {sent} club member(s).")
            except (SMTPException, OSError):
                logger.exception("Could not send event announcement for event %s", event.pk)
                messages.error(
                    request,
                    "The event was saved, but the email update could not be sent. Check email settings.",
                )
        messages.success(request, "Your club event is published.")
        return redirect("event_detail", event_id=event.pk)
    return render(
        request,
        "form.html",
        {"form": form, "title": f"Create an event for {club.name}", "club": club},
    )


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def event_edit(request, event_id):
    event = get_object_or_404(Event.objects.select_related("club"), pk=event_id)
    if not can_manage_club(request.user, event.club):
        messages.error(request, "You do not manage this club’s events.")
        return redirect("dashboard")
    original_starts_at = event.starts_at
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if form.is_valid():
        event = form.save()
        if event.starts_at != original_starts_at:
            event.registrations.filter(
                status=Registration.Status.REGISTERED
            ).update(reminder_sent=False)
        if event.published:
            try:
                sent = notify_club_members(request, event, changed=True)
                if sent:
                    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
                        messages.warning(
                            request,
                            f"Update email content for {sent} club member(s) was printed to the server terminal, not delivered. Configure SMTP to send it.",
                        )
                    else:
                        messages.info(request, f"Update emailed to {sent} club member(s).")
            except (SMTPException, OSError):
                logger.exception("Could not send event update for event %s", event.pk)
                messages.error(
                    request,
                    "Changes were saved, but the email update could not be sent. Check email settings.",
                )
        messages.success(request, "The event details have been updated.")
        return redirect("event_detail", event_id=event.pk)
    return render(
        request,
        "form.html",
        {
            "form": form,
            "title": f"Edit {event.title}",
            "club": event.club,
        },
    )


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def event_delete(request, event_id):
    if request.method != "POST":
        return redirect("dashboard")
    event = get_object_or_404(Event.objects.select_related("club"), pk=event_id)
    if not can_manage_club(request.user, event.club):
        messages.error(request, "You do not manage this club’s events.")
        return redirect("dashboard")
    club_id = event.club_id
    title = event.title
    event.delete()
    messages.success(request, f"{title} has been deleted.")
    return redirect("club_detail", club_id=club_id)


@roles_required(User.Role.STUDENT)
def register_event(request, event_id):
    if request.method != "POST":
        return redirect("event_detail", event_id=event_id)
    event = get_object_or_404(Event, pk=event_id, published=True)
    if not request.user.email:
        messages.error(
            request,
            "A registered email address is required. Ask the campus admin to add your email before registering.",
        )
    elif not event.is_upcoming:
        messages.error(request, "Registration for this event has closed.")
    elif Registration.objects.filter(
        event=event, status=Registration.Status.REGISTERED
    ).count() >= event.capacity:
        messages.error(request, "This event is full.")
    else:
        registration, created = Registration.objects.get_or_create(
            event=event,
            student=request.user,
            defaults={"status": Registration.Status.REGISTERED},
        )
        if not created and registration.status == Registration.Status.CANCELLED:
            registration.status = Registration.Status.REGISTERED
            registration.registered_at = timezone.now()
            registration.reminder_sent = False
            registration.save(update_fields=["status", "registered_at", "reminder_sent"])
        elif not created:
            messages.info(request, "You’re already registered for this event.")
            return redirect("event_detail", event_id=event.pk)
        try:
            sent = send_event_email(event, request.user.email, "confirmed")
            if sent != 1:
                raise SMTPException("Email backend did not confirm delivery.")
            if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
                messages.warning(
                    request,
                    "Your place is registered, but the confirmation was only printed to the server terminal, not delivered. Configure SMTP to email you.",
                )
            else:
                messages.success(
                    request, f"Your place is registered. Confirmation sent to {request.user.email}."
                )
        except (SMTPException, OSError):
            logger.exception(
                "Could not send registration email for student %s and event %s",
                request.user.pk,
                event.pk,
            )
            messages.error(
                request,
                "Your registration is saved, but the confirmation email could not be sent. Check your email settings.",
            )
    return redirect("event_detail", event_id=event.pk)


@roles_required(User.Role.STUDENT)
def cancel_registration(request, event_id):
    if request.method == "POST":
        registration = get_object_or_404(
            Registration,
            event_id=event_id,
            student=request.user,
            status=Registration.Status.REGISTERED,
        )
        registration.status = Registration.Status.CANCELLED
        registration.save(update_fields=["status"])
        messages.success(request, "Your event registration has been cancelled.")
    return redirect("event_detail", event_id=event_id)


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def attendees(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not can_manage_club(request.user, event.club):
        messages.error(request, "You do not manage this club’s event.")
        return redirect("dashboard")
    registrations = event.registrations.filter(
        status=Registration.Status.REGISTERED
    ).select_related("student")
    return render(
        request, "attendees.html", {"event": event, "registrations": registrations}
    )


def club_list(request):
    clubs = Club.objects.annotate(member_count=Count("members"))
    query = request.GET.get("q", "").strip()
    if query:
        clubs = clubs.filter(Q(name__icontains=query) | Q(description__icontains=query))
    return render(request, "clubs.html", {"clubs": clubs, "query": query})


def club_detail(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    application = None
    is_member = False
    if request.user.is_authenticated:
        application = MembershipApplication.objects.filter(
            club=club, student=request.user
        ).first()
        is_member = club.members.filter(pk=request.user.pk).exists()
    return render(
        request,
        "club_detail.html",
        {
            "club": club,
            "events": club.events.filter(published=True).select_related("organizer"),
            "application": application,
            "is_member": is_member,
            "can_manage": request.user.is_authenticated
            and can_manage_club(request.user, club),
            "can_administer": request.user.is_authenticated
            and can_administer_club(request.user, club),
        },
    )


@roles_required(User.Role.ADMIN)
def club_create(request):
    form = ClubForm(request.POST or None)
    if form.is_valid():
        club = form.save()
        messages.success(request, f"{club.name} has been created.")
        return redirect("club_detail", club_id=club.pk)
    return render(request, "form.html", {"form": form, "title": "Create a club"})


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN)
def club_edit(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    if not can_administer_club(request.user, club):
        messages.error(request, "Only this club’s administrator can edit its setup.")
        return redirect("club_detail", club_id=club.pk)
    form = ClubForm(request.POST or None, instance=club)
    if request.user.role != User.Role.ADMIN and not request.user.is_superuser:
        form.fields.pop("administrators")
    if form.is_valid():
        club = form.save()
        messages.success(request, "Club details and team assignments have been updated.")
        return redirect("club_detail", club_id=club.pk)
    return render(
        request, "form.html", {"form": form, "title": f"Manage {club.name}", "club": club}
    )


@roles_required(User.Role.STUDENT)
def apply_to_club(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    if club.members.filter(pk=request.user.pk).exists():
        messages.info(request, "You are already a member of this club.")
        return redirect("club_detail", club_id=club.pk)
    application = MembershipApplication.objects.filter(
        club=club, student=request.user
    ).first()
    if application and application.status == MembershipApplication.Status.APPROVED:
        messages.info(request, "Your club membership is already active.")
        return redirect("club_detail", club_id=club.pk)
    form = ClubApplicationForm(request.POST or None, instance=application)
    if form.is_valid():
        application = form.save(commit=False)
        application.club = club
        application.student = request.user
        application.status = MembershipApplication.Status.PENDING
        application.reviewed_at = None
        application.save()
        messages.success(request, "Your membership / audition application has been sent.")
        return redirect("club_detail", club_id=club.pk)
    return render(
        request,
        "form.html",
        {"form": form, "title": f"Apply to {club.name}", "club": club},
    )


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def applications(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    if not can_manage_club(request.user, club):
        messages.error(request, "You do not manage this club.")
        return redirect("dashboard")
    applications_list = club.applications.select_related("student")
    return render(
        request,
        "applications.html",
        {"club": club, "applications": applications_list},
    )


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def review_application(request, application_id, decision):
    if request.method != "POST" or decision not in {"approve", "reject"}:
        return redirect("dashboard")
    application = get_object_or_404(
        MembershipApplication.objects.select_related("club", "student"),
        pk=application_id,
    )
    if not can_manage_club(request.user, application.club):
        messages.error(request, "You do not manage this club’s applications.")
        return redirect("dashboard")
    if application.status != MembershipApplication.Status.PENDING:
        messages.info(request, "This application has already been reviewed.")
        return redirect("applications", club_id=application.club_id)
    application.status = (
        MembershipApplication.Status.APPROVED
        if decision == "approve"
        else MembershipApplication.Status.REJECTED
    )
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_at"])
    if decision == "approve":
        application.club.members.add(application.student)
    Notification.objects.create(
        recipient=application.student,
        message=f"Your application to {application.club.name} was "
        f"{'approved' if decision == 'approve' else 'reviewed'}.",
        url=f"/clubs/{application.club_id}/",
    )
    if application.student.email:
        try:
            send_mail(
                subject=f"Your {application.club.name} application",
                message=f"Your application to {application.club.name} was "
                f"{'approved' if decision == 'approve' else 'reviewed'}.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[application.student.email],
                fail_silently=False,
            )
        except (SMTPException, OSError):
            logger.exception(
                "Could not email application decision for application %s",
                application.pk,
            )
            messages.error(
                request,
                "The decision was saved, but the student email could not be sent.",
            )
    messages.success(request, "Application decision saved.")
    return redirect("applications", club_id=application.club_id)


@roles_required(User.Role.ADMIN)
def people(request):
    query = request.GET.get("q", "").strip()
    users = User.objects.all().order_by("role", "username")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    return render(request, "people.html", {"people": users, "query": query})


@roles_required(User.Role.ADMIN)
def create_account(request):
    form = CreateAccountForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "The account has been created.")
        return redirect("people")
    return render(
        request, "form.html", {"form": form, "title": "Create a campus account"}
    )


@roles_required(User.Role.ADMIN)
def update_role(request, user_id):
    person = get_object_or_404(User, pk=user_id)
    if person.is_superuser:
        messages.error(request, "Superuser access must be managed from Django administration.")
        return redirect("people")
    if request.method == "POST":
        form = AccountRoleForm(request.POST, instance=person)
        if form.is_valid():
            form.save()
            messages.success(request, "Account access has been updated.")
        else:
            messages.error(request, "Account access could not be updated.")
    return redirect("people")


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def reports(request):
    events = report_event_queryset(request)
    period = request.GET.get("period", "all")
    return render(
        request,
        "reports.html",
        {
            "events": events,
            "period": period,
            "total_events": events.count(),
            "total_attendees": sum(event.attendee_total for event in events),
        },
    )


def report_event_queryset(request):
    events = Event.objects.all().annotate(
        attendee_total=Count(
            "registrations",
            filter=Q(registrations__status=Registration.Status.REGISTERED),
        )
    )
    if request.user.role not in {User.Role.ADMIN} and not request.user.is_superuser:
        club_ids = request.user.administered_clubs.values_list("pk", flat=True)
        coordinator_club_ids = request.user.coordinated_clubs.values_list("pk", flat=True)
        events = events.filter(club_id__in=set(club_ids) | set(coordinator_club_ids))
    period = request.GET.get("period", "all")
    if period == "month":
        events = events.filter(starts_at__gte=timezone.now() - timedelta(days=30))
    elif period == "year":
        events = events.filter(starts_at__year=timezone.localdate().year)
    return events.order_by("-starts_at")


@roles_required(User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR)
def download_report(request):
    events = report_event_queryset(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="campus-event-report.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        ["Club", "Event", "Category", "Venue", "Starts", "Capacity", "Registrations"]
    )
    for event in events.order_by("starts_at"):
        writer.writerow(
            [
                event.club.name,
                event.title,
                event.get_category_display(),
                event.venue,
                timezone.localtime(event.starts_at).strftime("%Y-%m-%d %H:%M"),
                event.capacity,
                event.attendee_total,
            ]
        )
    return response


@roles_required(
    User.Role.ADMIN, User.Role.CLUB_ADMIN, User.Role.COORDINATOR, User.Role.STUDENT
)
def notifications(request):
    Notification.objects.filter(recipient=request.user, read=False).update(read=True)
    items = Notification.objects.filter(recipient=request.user)
    return render(request, "notifications.html", {"notifications": items})


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    first_account_setup = not User.objects.filter(
        Q(role=User.Role.ADMIN) | Q(is_superuser=True)
    ).exists()
    form = SignUpForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        if first_account_setup:
            user.role = User.Role.ADMIN
            user.save(update_fields=["role"])
        login(request, user)
        messages.success(
            request,
            "Your administrator account is ready."
            if first_account_setup
            else "Your student account is ready.",
        )
        return redirect("dashboard")
    return render(
        request,
        "registration/signup.html",
        {"form": form, "first_account_setup": first_account_setup},
    )

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone


EMAIL_COPY = {
    "confirmed": (
        "Registration confirmed",
        "You’re on the list!",
        "Your event place is confirmed. We’re looking forward to seeing you there.",
        "View event details",
    ),
    "reminder": (
        "Event reminder",
        "It’s almost time!",
        "Here’s a reminder about the event you registered for.",
        "Review event details",
    ),
    "announcement": (
        "New event",
        "Something’s happening!",
        "A new event has been published by one of your campus clubs.",
        "Explore event",
    ),
    "updated": (
        "Event update",
        "Plans have changed",
        "There’s an update to an event connected to your club.",
        "See the latest details",
    ),
}


def send_event_email(event, recipient, kind):
    subject_label, heading, intro, button_label = EMAIL_COPY[kind]
    site_base_url = settings.SITE_BASE_URL.rstrip("/")
    event_url = f"{site_base_url}{reverse('event_detail', args=[event.pk])}"
    poster_url = f"{site_base_url}{event.poster.url}" if event.poster else ""
    starts_at = timezone.localtime(event.starts_at)
    context = {
        "event": event,
        "subject_label": subject_label,
        "heading": heading,
        "intro": intro,
        "button_label": button_label,
        "event_url": event_url,
        "poster_url": poster_url,
        "starts_at": starts_at,
        "ends_at": timezone.localtime(event.ends_at),
    }
    message = (
        f"{intro}\n\n"
        f"{event.title} — {event.club.name}\n"
        f"When: {starts_at.strftime('%A, %B %d at %I:%M %p')}\n"
        f"Where: {event.venue}\n\n"
        f"{button_label}: {event_url}"
    )
    email = EmailMultiAlternatives(
        subject=f"{subject_label}: {event.title}",
        body=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    email.attach_alternative(
        render_to_string("emails/event_update.html", context),
        "text/html",
    )
    return email.send(fail_silently=False)

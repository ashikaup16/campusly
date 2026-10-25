from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from portal.event_emails import send_event_email
from portal.models import Registration


class Command(BaseCommand):
    help = "Email registered students a reminder before their upcoming events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Send a one-time reminder when an event is within this many hours.",
        )

    def handle(self, *args, **options):
        if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
            raise CommandError(
                "Email is using Django's console backend, so reminders cannot reach students. "
                "Configure SMTP and restart Django before sending reminders."
            )

        hours = options["hours"]
        if hours < 1:
            raise CommandError("--hours must be at least 1.")

        now = timezone.now()
        due_registrations = Registration.objects.filter(
            status=Registration.Status.REGISTERED,
            reminder_sent=False,
            student__is_active=True,
            event__published=True,
            event__starts_at__gt=now,
            event__starts_at__lte=now + timedelta(hours=hours),
        )
        missing_email_count = due_registrations.filter(student__email="").count()
        if missing_email_count:
            self.stderr.write(
                self.style.WARNING(
                    f"Skipped {missing_email_count} due registration(s) without a student email address."
                )
            )

        registrations = (
            due_registrations.exclude(student__email="")
            .select_related("student", "event", "event__club")
            .order_by("event__starts_at")
        )

        sent_count = 0
        for registration in registrations.iterator():
            event = registration.event
            sent = send_event_email(event, registration.student.email, "reminder")
            if sent != 1:
                raise CommandError(
                    f"Email backend did not confirm delivery to registration {registration.pk}."
                )
            registration.reminder_sent = True
            registration.save(update_fields=["reminder_sent"])
            sent_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Sent {sent_count} event reminder email(s).")
        )

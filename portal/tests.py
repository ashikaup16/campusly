from datetime import timedelta
from io import StringIO

from django.contrib.messages import get_messages
from django.core import mail
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.test import override_settings

from .models import (
    Club,
    Event,
    MembershipApplication,
    Notification,
    Registration,
    User,
)


class PortalWorkflowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student",
            password="test-password-123",
            email="student@example.test",
            role=User.Role.STUDENT,
        )
        self.coordinator = User.objects.create_user(
            username="coordinator",
            password="test-password-123",
            role=User.Role.COORDINATOR,
        )
        self.club = Club.objects.create(
            name="Creative Crew",
            description="Make things together.",
        )
        self.club.coordinators.add(self.coordinator)
        self.event = Event.objects.create(
            title="Campus Night",
            description="Music and friends.",
            category=Event.Category.CULTURE,
            venue="Main Quad",
            starts_at=timezone.now() + timedelta(days=4),
            ends_at=timezone.now() + timedelta(days=4, hours=2),
            capacity=2,
            club=self.club,
            organizer=self.coordinator,
        )

    def test_home_and_event_listing_render(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        response = self.client.get(reverse("event_list"), {"q": "Campus"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campus Night")

    def test_homepage_shows_all_three_dashboards_and_role_logins(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin dashboard")
        self.assertContains(response, "Coordinator dashboard")
        self.assertContains(response, "Student dashboard")
        self.assertContains(response, "Create admin account")
        self.assertContains(response, "Create student account")
        self.assertContains(response, "Coordinator log in")

    def test_homepage_shows_admin_account_creation_controls_to_admin(self):
        administrator = User.objects.create_user(
            username="campus-admin",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        self.client.force_login(administrator)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Create coordinator account")
        self.assertNotContains(response, "Create admin account")

    def test_signed_in_users_can_still_open_homepage(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student dashboard")

    def test_student_registration_and_cancellation(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("register_event", args=[self.event.pk])
        )
        self.assertRedirects(response, reverse("event_detail", args=[self.event.pk]))
        registration = Registration.objects.get(event=self.event, student=self.student)
        self.assertEqual(registration.status, Registration.Status.REGISTERED)

        response = self.client.post(
            reverse("cancel_registration", args=[self.event.pk])
        )
        self.assertRedirects(response, reverse("event_detail", args=[self.event.pk]))
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CANCELLED)

    def test_unapproved_student_can_see_and_register_for_public_event(self):
        self.client.force_login(self.student)
        event_list = self.client.get(reverse("event_list"))
        self.assertContains(event_list, "Campus Night")
        detail = self.client.get(reverse("event_detail", args=[self.event.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Club membership is required to register")
        response = self.client.post(reverse("register_event", args=[self.event.pk]))
        self.assertRedirects(response, reverse("event_detail", args=[self.event.pk]))
        self.assertTrue(
            Registration.objects.filter(
                event=self.event,
                student=self.student,
                status=Registration.Status.REGISTERED,
            ).exists()
        )
        self.assertNotIn(self.student, self.club.members.all())

    def test_student_dashboard_shows_events_without_club_membership(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campus Night")

    def test_students_cannot_open_coordinator_attendee_list(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("attendees", args=[self.event.pk]))
        self.assertRedirects(response, reverse("dashboard"))

    def test_coordinator_can_view_own_attendee_list(self):
        Registration.objects.create(event=self.event, student=self.student)
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("attendees", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student")

    def test_report_download_is_available_to_coordinator(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("download_report"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Campus Night", response.content.decode("utf-8-sig"))

    def test_report_download_uses_the_selected_date_filter(self):
        Event.objects.create(
            title="Archived Campus Night",
            description="An older event.",
            category=Event.Category.CULTURE,
            venue="Old Quad",
            starts_at=timezone.now() - timedelta(days=60),
            ends_at=timezone.now() - timedelta(days=60) + timedelta(hours=2),
            capacity=20,
            club=self.club,
            organizer=self.coordinator,
        )
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("download_report"), {"period": "month"})
        content = response.content.decode("utf-8-sig")
        self.assertIn("Campus Night", content)
        self.assertNotIn("Archived Campus Night", content)

    def test_student_applies_before_becoming_a_club_member(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("apply_to_club", args=[self.club.pk]),
            {"note": "I would love to audition for the club."},
        )
        self.assertRedirects(response, reverse("club_detail", args=[self.club.pk]))
        application = MembershipApplication.objects.get(
            club=self.club, student=self.student
        )
        self.assertEqual(application.status, MembershipApplication.Status.PENDING)
        self.assertNotIn(self.student, self.club.members.all())

    def test_coordinator_can_review_audition_and_approve_membership(self):
        application = MembershipApplication.objects.create(
            club=self.club, student=self.student, note="Audition details."
        )
        self.client.force_login(self.coordinator)
        response = self.client.post(
            reverse("review_application", args=[application.pk, "approve"])
        )
        self.assertRedirects(response, reverse("applications", args=[self.club.pk]))
        application.refresh_from_db()
        self.assertEqual(application.status, MembershipApplication.Status.APPROVED)
        self.assertIn(self.student, self.club.members.all())
        self.assertTrue(Notification.objects.filter(recipient=self.student).exists())

    def test_coordinator_cannot_manage_unassigned_club(self):
        other_club = Club.objects.create(name="Other club", description="Other community.")
        self.client.force_login(self.coordinator)
        response = self.client.get(
            reverse("event_create", args=[other_club.pk])
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_role_dashboards_and_club_pages_render(self):
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("club_detail", args=[self.club.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("applications", args=[self.club.pk])).status_code,
            200,
        )
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("apply_to_club", args=[self.club.pk])).status_code,
            200,
        )

    def test_club_admin_can_manage_assigned_club(self):
        club_admin = User.objects.create_user(
            username="club-admin",
            password="test-password-123",
            role=User.Role.CLUB_ADMIN,
        )
        self.club.administrators.add(club_admin)
        self.client.force_login(club_admin)
        response = self.client.get(reverse("club_edit", args=[self.club.pk]))
        self.assertEqual(response.status_code, 200)

    def test_administrator_can_create_a_coordinator_account(self):
        administrator = User.objects.create_user(
            username="campus-admin",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        self.client.force_login(administrator)
        response = self.client.post(
            reverse("create_account"),
            {
                "username": "new-coordinator",
                "first_name": "New",
                "last_name": "Coordinator",
                "email": "coordinator@example.test",
                "department": "Arts",
                "role": User.Role.COORDINATOR,
                "password1": "Strong-test-pass-3982",
                "password2": "Strong-test-pass-3982",
            },
        )
        self.assertRedirects(response, reverse("people"))
        account = User.objects.get(username="new-coordinator")
        self.assertEqual(account.role, User.Role.COORDINATOR)
        self.assertTrue(account.check_password("Strong-test-pass-3982"))

    def test_administrator_can_assign_coordinator_when_creating_club(self):
        administrator = User.objects.create_user(
            username="campus-admin",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        self.client.force_login(administrator)
        response = self.client.post(
            reverse("club_create"),
            {
                "name": "New arts club",
                "category": "Arts",
                "description": "A new campus community.",
                "emoji": "🎨",
                "coordinators": [str(self.coordinator.pk)],
                "administrators": [],
            },
        )
        self.assertEqual(response.status_code, 302)
        club = Club.objects.get(name="New arts club")
        self.assertIn(self.coordinator, club.coordinators.all())

    def test_administrator_can_assign_coordinator_when_editing_club(self):
        administrator = User.objects.create_user(
            username="campus-admin",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        self.client.force_login(administrator)
        response = self.client.post(
            reverse("club_edit", args=[self.club.pk]),
            {
                "name": self.club.name,
                "category": self.club.category,
                "description": self.club.description,
                "emoji": self.club.emoji,
                "coordinators": [str(self.coordinator.pk)],
                "administrators": [],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.coordinator, self.club.coordinators.all())

    def test_administrator_can_update_student_email(self):
        administrator = User.objects.create_user(
            username="email-admin",
            role=User.Role.ADMIN,
        )
        self.client.force_login(administrator)

        response = self.client.post(
            reverse("update_role", args=[self.student.pk]),
            {
                "email": "updated@example.test",
                "role": User.Role.STUDENT,
                "department": "Design",
                "is_active": "True",
            },
        )

        self.assertRedirects(response, reverse("people"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "updated@example.test")

    def test_coordinator_can_edit_own_club_event(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("event_edit", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)

    def test_coordinator_can_delete_event_in_assigned_club(self):
        self.client.force_login(self.coordinator)
        response = self.client.post(reverse("event_delete", args=[self.event.pk]))
        self.assertRedirects(response, reverse("club_detail", args=[self.club.pk]))
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())

    def test_coordinator_cannot_delete_another_clubs_event(self):
        other_club = Club.objects.create(name="Other club", description="Other community.")
        other_event = Event.objects.create(
            title="Other event",
            description="Not assigned to coordinator.",
            venue="Other venue",
            starts_at=timezone.now() + timedelta(days=4),
            ends_at=timezone.now() + timedelta(days=4, hours=2),
            club=other_club,
            organizer=self.coordinator,
        )
        self.client.force_login(self.coordinator)
        response = self.client.post(reverse("event_delete", args=[other_event.pk]))
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(Event.objects.filter(pk=other_event.pk).exists())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="portal@example.test",
        SITE_BASE_URL="http://127.0.0.1:8765",
    )
    def test_event_registration_emails_confirmation_to_student(self):
        self.club.members.add(self.student)
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("register_event", args=[self.event.pk])
        )
        self.assertRedirects(response, reverse("event_detail", args=[self.event.pk]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["student@example.test"])
        self.assertIn("Campus Night", mail.outbox[0].subject)
        self.assertIn("http://127.0.0.1:8765/events/", mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        self.assertIn(
            'href="http://127.0.0.1:8765/events/',
            mail.outbox[0].alternatives[0][0],
        )
        self.assertEqual(
            self.client.get(reverse("event_detail", args=[self.event.pk])).status_code,
            200,
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="portal@example.test",
        SITE_BASE_URL="https://campus.example.test",
    )
    def test_event_reminder_command_emails_due_registered_student_once(self):
        self.event.starts_at = timezone.now() + timedelta(hours=12)
        self.event.save(update_fields=["starts_at"])
        registration = Registration.objects.create(
            event=self.event,
            student=self.student,
        )

        call_command("send_event_reminders")
        call_command("send_event_reminders")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["student@example.test"])
        self.assertIn("Campus Night", mail.outbox[0].subject)
        self.assertIn("https://campus.example.test/events/", mail.outbox[0].body)
        self.assertIn(
            'href="https://campus.example.test/events/',
            mail.outbox[0].alternatives[0][0],
        )
        registration.refresh_from_db()
        self.assertTrue(registration.reminder_sent)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="portal@example.test",
    )
    def test_event_reminder_command_skips_not_due_cancelled_and_missing_email(self):
        self.event.starts_at = timezone.now() + timedelta(hours=12)
        self.event.save(update_fields=["starts_at"])
        self.student.email = ""
        self.student.save(update_fields=["email"])
        Registration.objects.create(event=self.event, student=self.student)

        other_student = User.objects.create_user(
            username="other-student",
            email="other@example.test",
            role=User.Role.STUDENT,
        )
        cancelled = Registration.objects.create(
            event=self.event,
            student=other_student,
            status=Registration.Status.CANCELLED,
        )
        not_due_event = Event.objects.create(
            title="Later event",
            description="Not due yet.",
            venue="Main Quad",
            starts_at=timezone.now() + timedelta(days=4),
            ends_at=timezone.now() + timedelta(days=4, hours=2),
            club=self.club,
            organizer=self.coordinator,
        )
        not_due = Registration.objects.create(
            event=not_due_event,
            student=other_student,
        )

        errors = StringIO()
        call_command("send_event_reminders", stderr=errors)

        self.assertEqual(mail.outbox, [])
        self.assertIn("Skipped 1 due registration", errors.getvalue())
        cancelled.refresh_from_db()
        not_due.refresh_from_db()
        self.assertFalse(cancelled.reminder_sent)
        self.assertFalse(not_due.reminder_sent)

    def test_rescheduling_event_allows_registered_students_to_receive_new_reminder(self):
        registration = Registration.objects.create(
            event=self.event,
            student=self.student,
            reminder_sent=True,
        )
        self.client.force_login(self.coordinator)
        starts_at = timezone.localtime(
            self.event.starts_at + timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M")
        ends_at = timezone.localtime(
            self.event.ends_at + timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M")

        response = self.client.post(
            reverse("event_edit", args=[self.event.pk]),
            {
                "title": self.event.title,
                "category": self.event.category,
                "description": self.event.description,
                "venue": self.event.venue,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "capacity": self.event.capacity,
                "published": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        registration.refresh_from_db()
        self.assertFalse(registration.reminder_sent)

    def test_event_registration_requires_student_email_for_confirmation(self):
        self.student.email = ""
        self.student.save(update_fields=["email"])
        self.client.force_login(self.student)

        response = self.client.post(reverse("register_event", args=[self.event.pk]))

        self.assertRedirects(response, reverse("event_detail", args=[self.event.pk]))
        self.assertFalse(
            Registration.objects.filter(event=self.event, student=self.student).exists()
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_console_backend_warns_registration_email_is_not_delivered(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse("register_event", args=[self.event.pk]))

        self.assertRedirects(response, reverse("event_detail", args=[self.event.pk]))
        self.assertTrue(
            Registration.objects.filter(event=self.event, student=self.student).exists()
        )
        message_text = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("not delivered", message_text)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_reminder_command_refuses_console_backend_without_marking_reminder_sent(self):
        self.event.starts_at = timezone.now() + timedelta(hours=12)
        self.event.save(update_fields=["starts_at"])
        registration = Registration.objects.create(event=self.event, student=self.student)

        with self.assertRaisesMessage(CommandError, "cannot reach students"):
            call_command("send_event_reminders")

        registration.refresh_from_db()
        self.assertFalse(registration.reminder_sent)

    def test_first_signup_becomes_campus_administrator(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new-student",
                "first_name": "Jamie",
                "last_name": "Lee",
                "email": "jamie@example.test",
                "department": "Design",
                "password1": "Strong-test-pass-3982",
                "password2": "Strong-test-pass-3982",
            },
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(
            User.objects.get(username="new-student").role, User.Role.ADMIN
        )

    def test_signup_after_admin_exists_creates_student(self):
        User.objects.create_user(
            username="campus-admin",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new-student",
                "first_name": "Jamie",
                "last_name": "Lee",
                "email": "jamie@example.test",
                "department": "Design",
                "password1": "Strong-test-pass-3982",
                "password2": "Strong-test-pass-3982",
            },
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(
            User.objects.get(username="new-student").role, User.Role.STUDENT
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="portal@example.test",
    )
    def test_published_event_emails_approved_club_members(self):
        self.club.members.add(self.student)
        self.client.force_login(self.coordinator)
        starts_at = timezone.localtime(
            timezone.now() + timedelta(days=8)
        ).strftime("%Y-%m-%dT%H:%M")
        ends_at = timezone.localtime(
            timezone.now() + timedelta(days=8, hours=2)
        ).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("event_create", args=[self.club.pk]),
            {
                "title": "New club gathering",
                "category": Event.Category.COMMUNITY,
                "description": "A club update.",
                "venue": "Club room",
                "starts_at": starts_at,
                "ends_at": ends_at,
                "capacity": 25,
                "published": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["student@example.test"])
        self.assertIn("New club gathering", mail.outbox[0].body)
        self.assertIn(
            "http://127.0.0.1:8765/events/",
            mail.outbox[0].alternatives[0][0],
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.student, message__contains="New club gathering"
            ).exists()
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="portal@example.test",
    )
    def test_event_update_is_emailed_to_registered_student_not_website_notification(self):
        Registration.objects.create(event=self.event, student=self.student)
        self.client.force_login(self.coordinator)
        starts_at = timezone.localtime(self.event.starts_at).strftime("%Y-%m-%dT%H:%M")
        ends_at = timezone.localtime(self.event.ends_at).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("event_edit", args=[self.event.pk]),
            {
                "title": "Updated campus night",
                "category": self.event.category,
                "description": "Updated event details.",
                "venue": self.event.venue,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "capacity": self.event.capacity,
                "published": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["student@example.test"])
        self.assertIn("Updated campus night", mail.outbox[0].body)
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.student, message__contains="Updated event"
            ).exists()
        )

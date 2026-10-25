from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        CLUB_ADMIN = "club_admin", "Club administrator"
        COORDINATOR = "coordinator", "Coordinator"
        STUDENT = "student", "Student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    department = models.CharField(max_length=100, blank=True)
    objects = UserManager()

    @property
    def display_role(self):
        return "Administrator" if self.is_superuser else self.get_role_display()


class Club(models.Model):
    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=60, default="Community")
    description = models.TextField()
    emoji = models.CharField(max_length=12, default="🎉")
    administrators = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="administered_clubs",
    )
    coordinators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="coordinated_clubs"
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="joined_clubs"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Event(models.Model):
    class Category(models.TextChoices):
        CULTURE = "culture", "Culture"
        TECHNOLOGY = "technology", "Technology"
        SPORTS = "sports", "Sports"
        ACADEMIC = "academic", "Academic"
        COMMUNITY = "community", "Community"

    title = models.CharField(max_length=180)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.COMMUNITY)
    venue = models.CharField(max_length=180)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=100)
    poster = models.ImageField(upload_to="event-posters/", blank=True)
    club = models.ForeignKey(
        Club, on_delete=models.CASCADE, related_name="events"
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organized_events"
    )
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    @property
    def registered_count(self):
        return self.registrations.filter(status=Registration.Status.REGISTERED).count()

    @property
    def seats_left(self):
        return max(self.capacity - self.registered_count, 0)

    @property
    def fill_percentage(self):
        if not self.capacity:
            return 0
        return min(round(self.registered_count * 100 / self.capacity), 100)

    @property
    def is_upcoming(self):
        return self.starts_at >= timezone.now()


class Registration(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="registrations"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.REGISTERED
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "student"], name="unique_event_registration")
        ]

    def __str__(self):
        return f"{self.student} — {self.event}"


class MembershipApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Not selected"

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="applications")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="club_applications"
    )
    note = models.TextField(blank=True, max_length=1200)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["club", "student"], name="unique_club_application")
        ]

    def __str__(self):
        return f"{self.student} — {self.club} ({self.status})"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    message = models.CharField(max_length=240)
    url = models.CharField(max_length=240, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import Club, Event, MembershipApplication, User


class SignUpForm(UserCreationForm):
    email = forms.EmailField()
    department = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "department")


class EventForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    ends_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = Event
        fields = (
            "title",
            "category",
            "description",
            "venue",
            "starts_at",
            "ends_at",
            "capacity",
            "poster",
            "published",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "capacity": forms.NumberInput(attrs={"min": 1}),
            "poster": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("starts_at")
        end = cleaned.get("ends_at")
        if start and start < timezone.now():
            self.add_error("starts_at", "Choose a date and time in the future.")
        if start and end and end <= start:
            self.add_error("ends_at", "The end time must be after the start time.")
        return cleaned


class ClubForm(forms.ModelForm):
    administrators = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False, widget=forms.SelectMultiple
    )
    coordinators = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False, widget=forms.SelectMultiple
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["administrators"].queryset = User.objects.filter(
            role=User.Role.CLUB_ADMIN, is_active=True
        )
        self.fields["coordinators"].queryset = User.objects.filter(
            role=User.Role.COORDINATOR, is_active=True
        )

    class Meta:
        model = Club
        fields = ("name", "category", "description", "emoji", "administrators", "coordinators")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class ClubApplicationForm(forms.ModelForm):
    class Meta:
        model = MembershipApplication
        fields = ("note",)
        labels = {"note": "Tell the club about yourself / audition"}
        widgets = {
            "note": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Share your interests, experience, or audition details...",
                }
            )
        }


class CreateAccountForm(UserCreationForm):
    email = forms.EmailField()
    department = forms.CharField(max_length=100, required=False)
    role = forms.ChoiceField(choices=User.Role.choices)

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "department",
            "role",
        )


class AccountRoleForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("role", "department", "email", "is_active")

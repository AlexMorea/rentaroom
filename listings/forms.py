from django import forms
from django.contrib.auth.models import User
from .models import Profile, Room, RoomImage
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password


class UserRegisterForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "input", "placeholder": "Create a password"}
        ),
        help_text="",
    )
    role = forms.ChoiceField(
        choices=Profile.ROLE_CHOICES, widget=forms.Select(attrs={"class": "input"})
    )

    class Meta:
        model = User
        fields = ["username", "email", "password"]
        widgets = {
            "username": forms.TextInput(
                attrs={"class": "input", "placeholder": "Choose a username"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "input", "placeholder": "you@example.com"}
            ),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError("Email is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data.get("password") or ""
        validate_password(pwd)
        return pwd

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            profile, _ = Profile.objects.get_or_create(
                user=user, defaults={"role": "tenant"}
            )
            profile.role = self.cleaned_data["role"]
            profile.save()
        return user


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = [
            "title",
            "description",
            "price",
            "location",
            "full_address",
            "postal_code",
            "room_type",
            "contact_phone",
            "contact_whatsapp",
            "contact_email",
            "total_units",
            "available_units",
            "availability_status",
            "available_from",
            "is_available",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. Spacious single room near TUT"}
            ),
            "price": forms.NumberInput(
                attrs={"class": "input", "placeholder": "e.g. 2500"}
            ),

            # PUBLIC, tenant-facing
            "location": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. Mamelodi East, Pretoria (public area)"}
            ),

            # PRIVATE, required for safety
            "full_address": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. 123 Tsutsuma St, Mamelodi East, Pretoria"}
            ),
            "postal_code": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. 0122"}
            ),

            "room_type": forms.Select(attrs={"class": "input"}),

            "contact_phone": forms.TextInput(
                attrs={"class": "input", "placeholder": "Call number e.g. +27 71 234 5678"}
            ),
            "contact_whatsapp": forms.TextInput(
                attrs={"class": "input", "placeholder": "WhatsApp number (optional) e.g. +27 71 234 5678"}
            ),
            "contact_email": forms.EmailInput(
                attrs={"class": "input", "placeholder": "Email (optional) e.g. landlord@gmail.com"}
            ),

            "total_units": forms.NumberInput(attrs={"class": "input", "min": 1}),
            "available_units": forms.NumberInput(attrs={"class": "input", "min": 0}),
            "availability_status": forms.Select(attrs={"class": "input"}),
            "available_from": forms.DateInput(attrs={"class": "input", "type": "date"}),

            "description": forms.Textarea(
                attrs={
                    "class": "input textarea",
                    "rows": 5,
                    "placeholder": "Describe the room, amenities, rules, and nearby transport...",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Required safety fields
        self.fields["full_address"].required = True
        self.fields["postal_code"].required = True

        # Better labels
        self.fields["total_units"].label = "Total units (identical rooms)"
        self.fields["available_units"].label = "Units available now"
        self.fields["availability_status"].label = "Availability status"
        self.fields["available_from"].label = "Available from (if occupied / next opening)"

        # Helpful guidance
        self.fields["location"].help_text = (
            "Public area only (tenants see this). Example: “Mamelodi East, Pretoria”. "
            "Do NOT put street number here."
        )
        self.fields["full_address"].help_text = (
            "Full street address for safety verification. Example: “123 Tsutsuma St, Mamelodi East, Pretoria”."
        )
        self.fields["postal_code"].help_text = (
            "Area / postal code. Example: “0122”."
        )
        self.fields["total_units"].help_text = (
            "If you have multiple identical rooms, enter the total number (e.g. 12). Otherwise leave as 1."
        )
        self.fields["available_units"].help_text = (
            "How many units are available right now (e.g. 6). If occupied, this will auto-set to 0."
        )
        self.fields["available_from"].help_text = (
            "Only needed if you choose “Occupied (available from)”."
        )

    def clean(self):
        cleaned = super().clean()

        # If no authenticated user (shouldn't happen for create/edit), just return
        if not self.user or not getattr(self.user, "is_authenticated", False):
            return cleaned

        title = (cleaned.get("title") or "").strip()
        location = (cleaned.get("location") or "").strip()
        room_type = cleaned.get("room_type")
        price = cleaned.get("price")

        # Availability validation
        status = cleaned.get("availability_status")
        total_units = cleaned.get("total_units") or 0
        available_units = cleaned.get("available_units") or 0
        available_from = cleaned.get("available_from")

        # ✅ Force occupied status behaviour server-side
        if status == "from":
            cleaned["available_units"] = 0
            available_units = 0

        # Basic rules
        if total_units < 1:
            self.add_error("total_units", "Total units must be at least 1.")

        if total_units and available_units > total_units:
            self.add_error("available_units", "Available units cannot exceed total units.")

        # Status-specific rules
        if status == "from":
            if not available_from:
                self.add_error("available_from", "Please set the date it becomes available.")
            # available_units is forced to 0, but keep message if it was tampered with
            if available_units != 0:
                self.add_error("available_units", "Units available now must be 0 for occupied listings.")

        if status == "mixed":
            if total_units and (available_units == 0 or available_units == total_units):
                self.add_error(
                    "available_units",
                    "For 'Some available now', set units between 1 and total_units-1."
                )

        # Duplicate protection (your existing logic)
        if not (title and location and room_type and price is not None):
            return cleaned

        qs = Room.objects.filter(
            owner=self.user,
            title__iexact=title,
            location__iexact=location,
            room_type=room_type,
            price=price,
        )

        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError(
                "You already posted a listing with the same title, location, type and price."
            )

        return cleaned


class RoomImageForm(forms.ModelForm):
    class Meta:
        model = RoomImage
        fields = ["image"]

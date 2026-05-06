from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from datetime import timedelta
from accounts.models import Membership
from .models import Profile, Room, RoomImage


class UserRegisterForm(forms.Form):
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "First name"})
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Last name"})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "input", "placeholder": "you@example.com"})
    )

    role = forms.ChoiceField(
        choices=Profile.ROLE_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
    )

    persona = forms.ChoiceField(
        choices=Profile.PERSONA_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )

    # 🔥 NEW PHONE INPUT (ALL USERS)
    country_code = forms.ChoiceField(
        choices=[("+27", "+27 🇿🇦"), ("+1", "+1 🇺🇸"), ("+44", "+44 🇬🇧")],
        initial="+27",
        widget=forms.Select(attrs={"class": "input"}),
    )

    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Phone number"})
    )

    # landlord extras
    alt_no = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Alternative number (optional)"}),
    )
    home_address = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Full home address"}),
    )
    postal_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Postal code"}),
    )

    terms_accepted = forms.BooleanField(
        required=False,
        label="I agree to the Terms & Conditions",
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Create a password"})
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Repeat password"})
    )

    # ---------------- VALIDATION ---------------- #

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered.")

        return email

    def clean(self):
        cleaned = super().clean()

        role = cleaned.get("role")
        p1 = cleaned.get("password1") or ""
        p2 = cleaned.get("password2") or ""

        if p1 != p2:
            self.add_error("password2", "Passwords do not match.")

        if p1:
            validate_password(p1)

        # 🔥 ALL USERS MUST HAVE PHONE
        if not cleaned.get("phone_number"):
            self.add_error("phone_number", "Phone number is required.")

        if role == "tenant":
            if not cleaned.get("persona"):
                self.add_error("persona", "Select your persona.")

        if role == "landlord":
            if not cleaned.get("home_address"):
                self.add_error("home_address", "Address required.")
            if not cleaned.get("postal_code"):
                self.add_error("postal_code", "Postal code required.")
            if not cleaned.get("terms_accepted"):
                self.add_error("terms_accepted", "You must accept terms.")

        return cleaned
    
    def save(self):
        email = (self.cleaned_data["email"] or "").strip().lower()
        first_name = (self.cleaned_data["first_name"] or "").strip()
        last_name = (self.cleaned_data["last_name"] or "").strip()

        user = User.objects.create(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        user.set_password(self.cleaned_data["password1"])
        user.is_active = False
        user.save()

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = self.cleaned_data["role"]

        # ✅ PERSONA (TENANT ONLY)
        if profile.role == "tenant":
            profile.persona = self.cleaned_data["persona"]

        # ✅ PHONE
        country_code = self.cleaned_data.get("country_code")
        phone_number = self.cleaned_data.get("phone_number")
        profile.country_code = country_code
        profile.phone_number = phone_number 

        # ✅ LANDLORD EXTRA

        if profile.role == "landlord":

            profile.alt_no = (self.cleaned_data.get("alt_no") or "").strip()
            profile.home_address = (self.cleaned_data.get("home_address") or "").strip()
            profile.postal_code = (self.cleaned_data.get("postal_code") or "").strip()
            profile.terms_accepted = True

        profile.save()

        # 🔥🔥🔥 CREATE MEMBERSHIP ONLY FOR LANDLORDS
        if profile.role == "landlord":
            Membership.objects.get_or_create(
                user=user,
                defaults={
                    "tier": "starter",
                    "is_active": True,
                    "is_trial": True,
                    "trial_start": timezone.now(),
                    "trial_end": timezone.now() + timedelta(days=30),
                    "status": "active"
                }
            )

        return user
    
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
        }

    # ✅ PREVENT DUPLICATE EMAILS
    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already in use.")

        return email


class ProfileUpdateForm(forms.ModelForm):
    COUNTRY_CHOICES = [
        ("+27", "+27 🇿🇦"),
        ("+1", "+1 🇺🇸"),
        ("+44", "+44 🇬🇧"),
    ]

    country_code = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        widget=forms.Select(attrs={"class": "input"})
    )

    phone_number = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "input"})
    )

    class Meta:
        model = Profile
        fields = [
            "persona",
            "phone_number",
            "alt_no",
            "home_address",
            "postal_code",
        ]
        widgets = {
            "persona": forms.Select(attrs={"class": "input"}),
            "alt_no": forms.TextInput(attrs={"class": "input"}),
            "home_address": forms.TextInput(attrs={"class": "input"}),
            "postal_code": forms.TextInput(attrs={"class": "input"}),
        }

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()

        if not phone.isdigit():
            raise forms.ValidationError("Enter a valid phone number (digits only).")

        return phone

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = [
            "title", "description", "price", "location", "full_address", "postal_code",
            "room_type", "contact_phone", "contact_whatsapp", "contact_email",
            "total_units", "available_units", "availability_status", "available_from",
            "is_available",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Spacious single room near TUT"}),
            "price": forms.NumberInput(attrs={"class": "input", "placeholder": "e.g. 2500"}),
            "location": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Mamelodi East, Pretoria (public area)"}),
            "full_address": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. 123 Tsutsuma St, Mamelodi East, Pretoria"}),
            "postal_code": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. 0122"}),
            "room_type": forms.Select(attrs={"class": "input"}),
            "contact_phone": forms.TextInput(attrs={"class": "input", "placeholder": "Call number e.g. +27 71 234 5678"}),
            "contact_whatsapp": forms.TextInput(attrs={"class": "input", "placeholder": "WhatsApp number (optional) e.g. +27 71 234 5678"}),
            "contact_email": forms.EmailInput(attrs={"class": "input", "placeholder": "Email (optional) e.g. landlord@gmail.com"}),
            "total_units": forms.NumberInput(attrs={"class": "input", "min": 1}),
            "available_units": forms.NumberInput(attrs={"class": "input", "min": 0}),
            "availability_status": forms.Select(attrs={"class": "input"}),
            "available_from": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "description": forms.Textarea(attrs={"class": "input textarea", "rows": 5, "placeholder": "Describe the room, amenities, rules, and nearby transport..."}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        self.fields["full_address"].required = True
        self.fields["postal_code"].required = True

        self.fields["total_units"].label = "Total units (identical rooms)"
        self.fields["available_units"].label = "Units available now"
        self.fields["availability_status"].label = "Availability status"
        self.fields["available_from"].label = "Available from (if occupied / next opening)"

        self.fields["location"].help_text = (
            "Public area only (tenants see this). Example: “Mamelodi East, Pretoria”. "
            "Do NOT put street number here."
        )
        self.fields["full_address"].help_text = (
            "Full street address for safety verification. Example: “123 Tsutsuma St, Mamelodi East, Pretoria”."
        )
        self.fields["postal_code"].help_text = "Area / postal code. Example: “0122”."
        self.fields["total_units"].help_text = "If you have multiple identical rooms, enter the total number (e.g. 12). Otherwise leave as 1."
        self.fields["available_units"].help_text = "How many units are available right now (e.g. 6). If occupied, this will auto-set to 0."
        self.fields["available_from"].help_text = "Only needed if you choose “Occupied (available from)”."

    def clean(self):
        cleaned = super().clean()

        if not self.user or not getattr(self.user, "is_authenticated", False):
            return cleaned

        title = (cleaned.get("title") or "").strip()
        location = (cleaned.get("location") or "").strip()
        room_type = cleaned.get("room_type")
        price = cleaned.get("price")

        status = cleaned.get("availability_status")
        total_units = cleaned.get("total_units") or 0
        available_units = cleaned.get("available_units") or 0
        available_from = cleaned.get("available_from")

        if status == "from":
            cleaned["available_units"] = 0
            available_units = 0

        if total_units < 1:
            self.add_error("total_units", "Total units must be at least 1.")

        if total_units and available_units > total_units:
            self.add_error("available_units", "Available units cannot exceed total units.")

        if status == "from":
            if not available_from:
                self.add_error("available_from", "Please set the date it becomes available.")
            if available_units != 0:
                self.add_error("available_units", "Units available now must be 0 for occupied listings.")

        if status == "mixed":
            if total_units and (available_units == 0 or available_units == total_units):
                self.add_error("available_units", "For 'Some available now', set units between 1 and total_units-1.")

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
            raise ValidationError("You already posted a listing with the same title, location, type and price.")

        return cleaned


class RoomImageForm(forms.ModelForm):
    class Meta:
        model = RoomImage
        fields = ["image"]


class ListingForm(forms.ModelForm):
    class Meta:
        model = Room
        exclude = ["owner", "created_at"]


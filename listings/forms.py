import re
from datetime import timedelta
from typing import ClassVar

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import Membership

from .models import Profile, Room, RoomImage
from .utils import normalize_sa_phone


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

    # NEW PHONE INPUT (ALL USERS)
    country_code = forms.ChoiceField(
        choices=[("+27", "+27 🇿🇦"), ("+1", "+1 🇺🇸"), ("+44", "+44 🇬🇧")],
        initial="+27",
        widget=forms.Select(attrs={"class": "input"}),
    )

    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Phone number",
            "inputmode": "tel",
            "autocomplete": "tel",
        })
    )

    # landlord extras
    alt_no = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Alternative number (optional)",
            "inputmode": "tel",
            "autocomplete": "tel",
        }),
    )
    home_address = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Full home address", "autocomplete": "street-address"}),
    )
    postal_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Postal code",
            "inputmode": "numeric",
            "autocomplete": "postal-code",
        }),
    )

    terms_accepted = forms.BooleanField(
        required=True,
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

        if not cleaned.get("phone_number"):
            self.add_error("phone_number", "Phone number is required.")


        # ================= GOOGLE ADDRESS VALIDATION =================
        # only validate for landlords
        if role == "landlord":
            home_address = cleaned.get("home_address")

            if not home_address:
                self.add_error(
                    "home_address",
                    "Please select a valid address from Google suggestions."
                )

            elif len(home_address.strip()) < 10:
                self.add_error(
                    "home_address",
                    "Address looks too short. Please select a valid Google address."
                )

                
        # ================= ROLE RULES =================
        if role == "tenant" and not cleaned.get("persona"):
            self.add_error("persona", "Select your persona.")

        if role == "landlord":
            if not cleaned.get("home_address"):
                self.add_error("home_address", "Address required.")
            if not cleaned.get("postal_code"):
                self.add_error("postal_code", "Postal code required.")

            # POPIA CONSENT ENFORCEMENT (GLOBAL RULE)
            if not cleaned.get("terms_accepted"):
                self.add_error(
                    "terms_accepted",
                    "You must accept the Terms of Service and Privacy Policy to continue."
                )

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

        # PERSONA (TENANT ONLY)
        if profile.role == "tenant":
            profile.persona = self.cleaned_data["persona"]

        # PHONE
        country_code = self.cleaned_data.get("country_code")
        phone_number = self.cleaned_data.get("phone_number")
        profile.country_code = country_code
        profile.phone_number = normalize_sa_phone(phone_number)

        # LANDLORD EXTRA
        if profile.role == "landlord":

            alt = (self.cleaned_data.get("alt_no") or "").strip()
            profile.alt_no = normalize_sa_phone(alt) if alt else ""
            profile.home_address = (self.cleaned_data.get("home_address") or "").strip()
            profile.postal_code = (self.cleaned_data.get("postal_code") or "").strip()
            profile.terms_accepted = self.cleaned_data["terms_accepted"]
            profile.terms_accepted_at = timezone.now()
            profile.privacy_accepted_at = timezone.now()

        profile.save()

        # CREATE MEMBERSHIP ONLY FOR LANDLORDS
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
        fields = ("first_name", "last_name")
        widgets: ClassVar[dict] = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already in use.")

        return email


class ProfileUpdateForm(forms.ModelForm):
    COUNTRY_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("+27", "+27 🇿🇦"),
        ("+1", "+1 🇺🇸"),
        ("+44", "+44 🇬🇧"),
    )

    country_code = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        widget=forms.Select(attrs={"class": "input"})
    )

    phone_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "inputmode": "tel", "autocomplete": "tel"})
    )

    class Meta:
        model = Profile
        fields = (
            "persona",
            "country_code",
            "phone_number",
            "alt_no",
            "home_address",
            "postal_code",
        )
        widgets: ClassVar[dict] = {
            "persona": forms.Select(attrs={"class": "input"}),
            "alt_no": forms.TextInput(attrs={"class": "input", "inputmode": "tel", "autocomplete": "tel"}),
            "home_address": forms.TextInput(attrs={"class": "input", "autocomplete": "street-address"}),
            "postal_code": forms.TextInput(attrs={"class": "input", "inputmode": "numeric", "autocomplete": "postal-code"}),
        }

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()

        if not phone:
            return self.instance.phone_number

        phone = re.sub(r"[^\d]", "", phone)

        phone = phone.removeprefix("27")

        phone = phone.removeprefix("0")

        if len(phone) != 9:
            raise forms.ValidationError("Enter valid SA number. Example: 841234567")

        return phone
        
class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields: ClassVar[list[str]] = [
            "title",
            "description",
            "price",
            "deposit_amount",

            "suburb",
            "town",
            "city",
            "province",

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

        widgets: ClassVar[dict] = {
            "title": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Spacious single room near TUT"
            }),

            "price": forms.NumberInput(attrs={
                "class": "input",
                "placeholder": "e.g. 2500"
            }),

            "deposit_amount": forms.NumberInput(attrs={
                "class": "input",
                "placeholder": "Leave blank if no deposit"
            }),

            "suburb": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Mamelodi East"
            }),

            "town": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Mamelodi"
            }),

            "city": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Pretoria"
            }),

            "province": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Gauteng"
            }),

            "location": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Mamelodi East, Pretoria (or select from map later)"
            }),

            "full_address": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. 123 Tsutsuma St"
            }),

            "postal_code": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. 0122",
                "inputmode": "numeric",
                "autocomplete": "postal-code"
            }),

            "room_type": forms.Select(attrs={
                "class": "input"
            }),

            "contact_phone": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. 0845643877",
                "inputmode": "tel",
                "autocomplete": "tel"
            }),

            "contact_whatsapp": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "optional",
                "inputmode": "tel",
                "autocomplete": "tel"
            }),

            "contact_email": forms.EmailInput(attrs={
                "class": "input",
                "placeholder": "optional"
            }),

            "total_units": forms.NumberInput(attrs={
                "class": "input",
                "min": 1
            }),

            "available_units": forms.NumberInput(attrs={
                "class": "input",
                "min": 0
            }),

            "availability_status": forms.Select(attrs={
                "class": "input"
            }),

            "available_from": forms.DateInput(attrs={
                "class": "input",
                "type": "date"
            }),

            "description": forms.Textarea(attrs={
                "class": "input textarea",
                "rows": 5,
                "placeholder": "Describe the room..."
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        self.fields["full_address"].required = True
        self.fields["postal_code"].required = True

        self.fields["suburb"].help_text = "Example: Mamelodi East"
        self.fields["town"].help_text = "Example: Mamelodi"
        self.fields["city"].help_text = "Example: Pretoria"
        self.fields["province"].help_text = "Example: Gauteng"

        self.fields["full_address"].help_text = (
            "Exact street address for Google Maps."
        )

        self.fields["total_units"].label = "Total units"
        self.fields["available_units"].label = "Units available now"

        # Client-side helper: mark contact fields required in the widget
        role = getattr(getattr(self.user, "profile", None), "role", None)

        if role == "landlord":
            for fld in ("contact_phone", "contact_whatsapp"):
                if fld in self.fields:
                    self.fields[fld].required = True
                    self.fields[fld].widget.attrs.setdefault("required", "required")

    def clean(self):
        cleaned = super().clean()

        if not self.user or not self.user.is_authenticated:
            return cleaned

        title = (cleaned.get("title") or "").strip()

        suburb = (cleaned.get("suburb") or "").strip()
        city = (cleaned.get("city") or "").strip()

        room_type = cleaned.get("room_type")
        price = cleaned.get("price")

        status = cleaned.get("availability_status")
        total_units = cleaned.get("total_units") or 0
        available_units = cleaned.get("available_units") or 0
        available_from = cleaned.get("available_from")

        # LOCATION PRIORITY SYSTEM (MVP SAFE)
        location = (cleaned.get("location") or "").strip()

        suburb = (cleaned.get("suburb") or "").strip()
        city = (cleaned.get("city") or "").strip()

        # If user did NOT manually enter location → auto-build it
        if not location and suburb and city:
            location = f"{suburb}, {city}"

        cleaned["location"] = location

        # PHONE NORMALIZER
        phone = normalize_sa_phone(cleaned.get("contact_phone"))
        if phone:
            cleaned["contact_phone"] = phone
        else:
            cleaned["contact_phone"] = ""

        if cleaned.get("contact_whatsapp"):
            whatsapp = normalize_sa_phone(cleaned.get("contact_whatsapp"))
            if whatsapp:
                cleaned["contact_whatsapp"] = whatsapp
            else:
                cleaned["contact_whatsapp"] = ""

        # Landlord must provide both contact phone and WhatsApp for listings
        try:
            role = getattr(self.user, "profile", None) and self.user.profile.role
        except AttributeError:
            role = None

        if role == "landlord":
            if not cleaned.get("contact_phone"):
                self.add_error(
                    "contact_phone",
                    "Landlords must provide a contact phone number."
                )
            if not cleaned.get("contact_whatsapp"):
                self.add_error(
                    "contact_whatsapp",
                    "Landlords must provide a WhatsApp number."
                )

        # availability
        if status == "from":
            cleaned["available_units"] = 0
            available_units = 0

        if total_units < 1:
            self.add_error(
                "total_units",
                "Total units must be at least 1."
            )

        if available_units > total_units:
            self.add_error(
                "available_units",
                "Available units cannot exceed total units."
            )

        if status == "from" and not available_from:
            self.add_error(
                "available_from",
                "Choose available date."
            )

        if status == "mixed" and (
            available_units == 0 or available_units == total_units
        ):
            self.add_error(
                "available_units",
                "Must be between 1 and total_units-1."
            )

        # duplicate protection
        if title and location and room_type and price:
            qs = Room.objects.filter(
                owner=self.user,
                title__iexact=title,
                location__iexact=location,
                room_type=room_type,
                price=price,
            )

            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(
                    "You already posted this listing."
                )
            
            if not cleaned.get("location"):
                self.add_error(
                    "location",
                    "Please enter a location (e.g. Mamelodi East, Pretoria)."
                )

        return cleaned


class RoomImageForm(forms.ModelForm):
    class Meta:
        model = RoomImage
        fields = ("image",)


class ListingForm(forms.ModelForm):
    class Meta:
        model = Room
        exclude = ("owner", "created_at")
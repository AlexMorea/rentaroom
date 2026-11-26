import re
import unicodedata
from typing import ClassVar

from django import forms
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import Membership

from .models import Profile, Room, RoomImage
from .utils import (
    PHONE_INVALID_MESSAGE,
    SA_PHONE_INVALID_MESSAGE,
    is_disposable_email,
    normalize_sa_phone,
    parse_phone,
    unique_username_for,
)


# No role is preselected on signup. The select used to default to
# "tenant" (the first choice) and sits hidden behind the role cards, so a
# landlord who didn't tap "Landlord" was silently registered as a tenant.
ROLE_FORM_CHOICES = [("", "Choose one"), *Profile.ROLE_CHOICES]
ROLE_REQUIRED_MESSAGE = "Please choose whether you're a tenant or a landlord."


class RoleCardSelect(forms.Select):
    """
    The role <select> on signup sits hidden behind the Tenant/Landlord
    cards. Rendered with `required`, a browser refuses to submit while
    it's empty but can't point at a hidden field, so tapping "Create
    account" without picking a card did nothing at all - no message, no
    request. The page's script asks for a role instead, and the form
    still rejects a missing one on the server.
    """

    def use_required_attribute(self, initial):
        return False


def _clean_phone_fields(form, cleaned, names, country_code: str | None = "+27"):
    """Validates and normalizes each named phone field that has a value
    (blank ones are left to the field's own required/optional rule)."""
    message = SA_PHONE_INVALID_MESSAGE if (country_code or "+27") == "+27" else PHONE_INVALID_MESSAGE
    for name in names:
        raw = (cleaned.get(name) or "").strip()
        if not raw:
            continue
        number = parse_phone(raw, country_code)
        if number is None:
            form.add_error(name, message)
        else:
            cleaned[name] = number


class ContactMessageForm(forms.Form):
    REASON_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("general", "General enquiry"),
        ("partnership", "Partnership"),
        ("media", "Media & Press"),
        ("support", "Support"),
    )

    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Your name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "input", "placeholder": "you@example.com"}),
    )
    reason = forms.ChoiceField(
        choices=REASON_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "input", "rows": 5, "placeholder": "How can we help?",
        }),
    )
    # Honeypot, same as UserRegisterForm.website: hidden from people,
    # filled in by bots that complete every field they find.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "class": "ct-hp-input", "tabindex": "-1", "autocomplete": "off",
    }))


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
        choices=ROLE_FORM_CHOICES,
        error_messages={"required": ROLE_REQUIRED_MESSAGE},
        widget=RoleCardSelect(attrs={"class": "input"}),
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

    # Separate from phone_number above - not everyone's WhatsApp is on
    # the same number as their primary phone. Optional for everyone
    # (tenant or landlord); falls back to phone_number when left blank
    # (see Profile.whatsapp_full_number()).
    whatsapp_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "WhatsApp number, if different (optional)",
            "inputmode": "tel",
            "autocomplete": "tel",
        }),
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

    # Honeypot - invisible to real users (hidden via CSS in register.html),
    # so only a scripted bot that blindly fills every input on the page
    # would ever populate it. register() checks this before touching the
    # form at all; it isn't validated here as "must be blank" on purpose -
    # a bot that finds and skips it shouldn't get a distinguishing error.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "class": "pr-hp-input", "tabindex": "-1", "autocomplete": "off",
    }))

    # ---------------- VALIDATION ---------------- #

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered.")

        if is_disposable_email(email):
            raise ValidationError(
                "Please sign up with an email address you'll keep using. "
                "We don't accept temporary or disposable inboxes."
            )

        return email

    def clean(self):
        cleaned = super().clean()

        role = cleaned.get("role")
        p1 = cleaned.get("password1") or ""
        p2 = cleaned.get("password2") or ""

        if p1 != p2:
            self.add_error("password2", "Passwords do not match.")

        if p1:
            # Attached to the password field (not raised), so the rest of
            # this method still runs and every problem shows at once.
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error("password1", exc)

        if not cleaned.get("phone_number") and "phone_number" not in self.errors:
            self.add_error("phone_number", "Phone number is required.")

        phone_fields = ["phone_number", "whatsapp_number"]
        if role == "landlord":
            phone_fields.append("alt_no")
        _clean_phone_fields(self, cleaned, phone_fields, cleaned.get("country_code"))

        # ================= LANDLORD ADDRESS =================
        # Used for landlord verification only, never shown publicly. Many
        # township addresses aren't in Google's suggestions, so a typed
        # address is fine as long as it has enough detail to verify.
        if role == "landlord":
            home_address = (cleaned.get("home_address") or "").strip()
            if not home_address:
                self.add_error("home_address", "Please enter your home address. We use it to verify landlords and never show it publicly.")
            elif len(home_address) < 10:
                self.add_error("home_address", "Please add a bit more detail to your address, such as the street and the area.")

        # ================= ROLE RULES =================
        if role == "tenant" and not cleaned.get("persona"):
            self.add_error("persona", "Select your persona.")

        if role == "landlord":
            if not cleaned.get("postal_code"):
                self.add_error("postal_code", "Please enter your postal code.")

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
            username=unique_username_for(email),
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

        whatsapp_number = (self.cleaned_data.get("whatsapp_number") or "").strip()
        profile.whatsapp_number = normalize_sa_phone(whatsapp_number) if whatsapp_number else ""

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
            Membership.objects.get_or_create(user=user)

        return user


class GoogleCompleteProfileForm(forms.Form):
    """
    Finishes a Google sign-in for a brand-new (or never-onboarded)
    account. Same fields as UserRegisterForm minus email/password - Google
    already gave us a verified email, and there's no password to set for
    a Google-authenticated account.
    """

    role = forms.ChoiceField(
        choices=ROLE_FORM_CHOICES,
        error_messages={"required": ROLE_REQUIRED_MESSAGE},
        widget=RoleCardSelect(attrs={"class": "input"}),
    )

    persona = forms.ChoiceField(
        choices=Profile.PERSONA_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )

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

    terms_accepted = forms.BooleanField(required=False)

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")

        if not cleaned.get("phone_number") and "phone_number" not in self.errors:
            self.add_error("phone_number", "Phone number is required.")

        phone_fields = ["phone_number", "alt_no"] if role == "landlord" else ["phone_number"]
        _clean_phone_fields(self, cleaned, phone_fields, cleaned.get("country_code"))

        if role == "tenant" and not cleaned.get("persona"):
            self.add_error("persona", "Select your persona.")

        if role == "landlord":
            if not cleaned.get("home_address"):
                self.add_error("home_address", "Please enter your home address. We use it to verify landlords and never show it publicly.")
            if not cleaned.get("postal_code"):
                self.add_error("postal_code", "Please enter your postal code.")
            if not cleaned.get("terms_accepted"):
                self.add_error(
                    "terms_accepted",
                    "You must accept the Terms of Service and Privacy Policy to continue."
                )

        return cleaned

    def apply_to(self, user):
        profile, _ = Profile.objects.get_or_create(user=user)

        profile.role = self.cleaned_data["role"]

        if profile.role == "tenant":
            profile.persona = self.cleaned_data["persona"]

        profile.country_code = self.cleaned_data.get("country_code")
        profile.phone_number = normalize_sa_phone(self.cleaned_data.get("phone_number"))

        if profile.role == "landlord":
            alt = (self.cleaned_data.get("alt_no") or "").strip()
            profile.alt_no = normalize_sa_phone(alt) if alt else ""
            profile.home_address = (self.cleaned_data.get("home_address") or "").strip()
            profile.postal_code = (self.cleaned_data.get("postal_code") or "").strip()
            profile.terms_accepted = self.cleaned_data["terms_accepted"]
            profile.terms_accepted_at = timezone.now()
            profile.privacy_accepted_at = timezone.now()

        # Google already verified this address - this step stands in for
        # the email-OTP step a normal signup goes through.
        profile.is_email_verified = True
        profile.is_phone_verified = True
        profile.save()

        if profile.role == "landlord":
            Membership.objects.get_or_create(user=user)

        return profile


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

    # Optional, separate from phone_number - see Profile.whatsapp_number.
    whatsapp_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "input", "inputmode": "tel", "autocomplete": "tel",
            "placeholder": "If different from your phone number",
        }),
    )

    class Meta:
        model = Profile
        fields = (
            "persona",
            "country_code",
            "phone_number",
            "whatsapp_number",
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

    def clean_whatsapp_number(self):
        # Optional - unlike phone_number, blank is a valid answer (falls
        # back to phone_number, see Profile.whatsapp_full_number()).
        whatsapp = (self.cleaned_data.get("whatsapp_number") or "").strip()

        if not whatsapp:
            return ""

        whatsapp = re.sub(r"[^\d]", "", whatsapp)
        whatsapp = whatsapp.removeprefix("27")
        whatsapp = whatsapp.removeprefix("0")

        if len(whatsapp) != 9:
            raise forms.ValidationError("Enter valid SA number. Example: 841234567")

        return whatsapp

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
                "placeholder": "Leave blank if it's the same number",
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
        try:
            role = getattr(self.user, "profile", None) and self.user.profile.role  # pyright: ignore[reportOptionalMemberAccess] - guarded by the getattr(...) and short-circuit above
        except AttributeError:
            role = None

        if role == "landlord":
            # The call number is required. WhatsApp is optional: when it's
            # blank, the listing's WhatsApp button uses the call number
            # (see track_contact), so asking twice only slows landlords down.
            self.fields["contact_phone"].required = True
            self.fields["contact_phone"].widget.attrs.setdefault("required", "required")

            # New listing: start from the number the landlord signed up with.
            profile = getattr(self.user, "profile", None)
            if not self.is_bound and not getattr(self.instance, "pk", None) and profile is not None:
                number = (getattr(profile, "phone_number", "") or "").strip()
                if number:
                    self.initial.setdefault("contact_phone", number)
                whatsapp = (getattr(profile, "whatsapp_number", "") or "").strip()
                if whatsapp:
                    self.initial.setdefault("contact_whatsapp", whatsapp)

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

        # PHONE NORMALIZER - a mistyped number goes back to the landlord to
        # fix rather than being published: tenants can't call or WhatsApp
        # a number with a digit missing.
        _clean_phone_fields(self, cleaned, ["contact_phone", "contact_whatsapp"])

        # Landlords must give a number tenants can call (WhatsApp falls back to it)
        try:
            role = getattr(self.user, "profile", None) and self.user.profile.role
        except AttributeError:
            role = None

        if role == "landlord":
            if not cleaned.get("contact_phone") and "contact_phone" not in self.errors:
                self.add_error(
                    "contact_phone",
                    "Landlords must provide a contact phone number."
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


class AccountPasswordResetForm(PasswordResetForm):
    """
    Django's reset form silently skips accounts without a usable password.
    Here those are Google sign-ups: someone who later tried email + password
    and then "Forgot password?" got the "check your inbox" page and no
    email, with no way in except Google. Owning the inbox is what a reset
    proves, so it's allowed for them too - it just gives them a password.
    """

    def get_users(self, email):
        # Same as Django's own get_users() minus the has_usable_password()
        # filter - including its Unicode-safe comparison, which stops a
        # look-alike address matching someone else's account.
        def folded(value):
            return unicodedata.normalize("NFKC", value or "").casefold()

        target = folded(email)
        return (
            user
            for user in User._default_manager.filter(email__iexact=email, is_active=True)
            if folded(user.email) == target
        )


class ResetPasswordForm(SetPasswordForm):
    """Forgot-password reset: once the new password is saved, every
    remembered device has to confirm by email again."""

    def save(self, commit=True):
        from accounts.devices import forget_devices

        user = super().save(commit=commit)
        if commit:
            forget_devices(user)
        return user


class BecomeLandlordForm(forms.Form):
    """Switches an existing tenant account to a landlord one, collecting
    the same verification details landlord signup asks for."""

    home_address = forms.CharField(
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Full home address", "autocomplete": "street-address"}),
    )
    postal_code = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "input", "placeholder": "Postal code", "inputmode": "numeric", "autocomplete": "postal-code",
        }),
    )
    alt_no = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Alternative number (optional)", "inputmode": "tel"}),
    )
    terms_accepted = forms.BooleanField(
        error_messages={"required": "You must accept the Terms of Service and Privacy Policy to continue."},
    )

    def clean_home_address(self):
        home_address = (self.cleaned_data.get("home_address") or "").strip()
        if len(home_address) < 10:
            raise ValidationError("Please add a bit more detail to your address, such as the street and the area.")
        return home_address

    def clean_alt_no(self):
        alt = (self.cleaned_data.get("alt_no") or "").strip()
        if not alt:
            return ""
        number = parse_phone(alt)
        if number is None:
            raise ValidationError(SA_PHONE_INVALID_MESSAGE)
        return number

    def apply_to(self, user):
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = "landlord"
        profile.home_address = self.cleaned_data["home_address"]
        profile.postal_code = self.cleaned_data["postal_code"].strip()
        alt = (self.cleaned_data.get("alt_no") or "").strip()
        profile.alt_no = normalize_sa_phone(alt) if alt else ""
        profile.terms_accepted = True
        profile.terms_accepted_at = timezone.now()
        profile.privacy_accepted_at = timezone.now()
        profile.save()

        Membership.objects.get_or_create(user=user)

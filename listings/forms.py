from django import forms
from django.contrib.auth.models import User
from .models import Profile, Room, RoomImage
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password


class UserRegisterForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        help_text="Use at least 8 characters and avoid simple passwords.",
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
            user.profile.role = self.cleaned_data["role"]
            user.profile.save()
        return user


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = [
            "title",
            "description",
            "price",
            "location",
            "room_type",
            "contact_phone",
            "contact_whatsapp",
            "contact_email",
            "is_available",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "e.g. Spacious single room near TUT",
                }
            ),
            "price": forms.NumberInput(
                attrs={"class": "input", "placeholder": "e.g. 2500"}
            ),
            "location": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. Mamelodi East"}
            ),
            "room_type": forms.Select(attrs={"class": "input"}),
            "contact_phone": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "Call number e.g. +27 71 234 5678",
                }
            ),
            "contact_whatsapp": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "WhatsApp number (optional) e.g. +27 71 234 5678",
                }
            ),
            "contact_email": forms.EmailInput(
                attrs={
                    "class": "input",
                    "placeholder": "Email (optional) e.g. landlord@gmail.com",
                }
            ),
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

    def clean(self):
        cleaned = super().clean()

        # if we don't have an owner yet, skip
        if not self.user or not getattr(self.user, "is_authenticated", False):
            return cleaned

        title = (cleaned.get("title") or "").strip()
        location = (cleaned.get("location") or "").strip()
        room_type = cleaned.get("room_type")
        price = cleaned.get("price")

        if not (title and location and room_type and price is not None):
            return cleaned

        qs = Room.objects.filter(
            owner=self.user,
            title__iexact=title,
            location__iexact=location,
            room_type=room_type,
            price=price,
        )

        # if editing, exclude self
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

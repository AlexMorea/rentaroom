from django import forms
from django.contrib.auth.models import User
from .models import Profile, Room, RoomImage


class UserRegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

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


class RoomImageForm(forms.ModelForm):
    class Meta:
        model = RoomImage
        fields = ["image"]

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
            "is_available",
        ]


class RoomImageForm(forms.ModelForm):
    class Meta:
        model = RoomImage
        fields = ["image"]

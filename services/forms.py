from django import forms
from .models import GuardianSession, BakkieDriver


class GuardianSessionForm(forms.ModelForm):
    class Meta:
        model = GuardianSession

        fields = [
            "destination",
            "emergency_contact_name",
            "emergency_contact_phone",
        ]

        widgets = {
            "destination": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Where are you going?"
            }),

            "emergency_contact_name": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Emergency contact name"
            }),

            "emergency_contact_phone": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Emergency phone number"
            }),
        }


class BakkieDriverForm(forms.ModelForm):
    licence_image = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={"class": "input"})
    )

    class Meta:
        model = BakkieDriver

        fields = [
            "full_name",
            "phone_number",
            "vehicle_type",
            "vehicle_registration",
            "city",
            "licence_image",
        ]

        widgets = {
            "full_name": forms.TextInput(attrs={"class": "input"}),
            "phone_number": forms.TextInput(attrs={"class": "input"}),
            "vehicle_type": forms.Select(attrs={"class": "input"}),
            "vehicle_registration": forms.TextInput(attrs={"class": "input"}),
            "city": forms.TextInput(attrs={"class": "input"}),
        }
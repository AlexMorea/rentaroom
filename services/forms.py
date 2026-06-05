from django import forms
from .models import GuardianSession, BakkieDriver, MoveBooking


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

    terms_accepted = forms.BooleanField(
        required=True,
        label="I agree to the Driver Terms and Privacy Policy"
    )

    class Meta:
        model = BakkieDriver

        fields = [
            "full_name",
            "email",
            "phone_number",
            "vehicle_type",
            "vehicle_registration",
            "address",
            "city",
            "province",
            "latitude",
            "longitude",
            "vehicle_image",
            "licence_image",
        ]

        widgets = {
            "full_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
            "phone_number": forms.TextInput(attrs={"class": "input"}),
            "vehicle_type": forms.Select(attrs={"class": "input"}),
            "vehicle_registration": forms.TextInput(attrs={"class": "input"}),
            "city": forms.TextInput(attrs={"class": "input"}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }

class MoveBookingForm(forms.ModelForm):

    class Meta:

        model = MoveBooking

        fields = [
            "pickup_location",
            "dropoff_location",
            "scheduled_time",
            "notes",
        ]

        widgets = {

            "pickup_location": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "Pickup location"
                }
            ),

            "dropoff_location": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "Drop-off location"
                }
            ),

            "scheduled_time": forms.DateTimeInput(
                attrs={
                    "class": "input",
                    "type": "datetime-local"
                }
            ),

            "notes": forms.Textarea(
                attrs={
                    "class": "input",
                    "rows": 4
                }
            ),
        }

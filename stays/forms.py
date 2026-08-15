from django import forms

from .models import GuestHouse, Booking


class GuestHouseForm(forms.ModelForm):
    class Meta:
        model = GuestHouse
        fields = [
            "name",
            "description",
            "price_per_night",
            "max_guests",
            "min_nights",

            "suburb",
            "town",
            "city",
            "province",

            "location",
            "full_address",
            "postal_code",

            "check_in_time",
            "check_out_time",
            "house_rules",

            "has_wifi",
            "has_parking",
            "has_breakfast",
            "has_pool",
            "has_aircon",
            "has_tv",

            "contact_phone",
            "contact_whatsapp",
            "contact_email",

            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Mama Thandi's Guest House"
            }),

            "description": forms.Textarea(attrs={
                "class": "input",
                "rows": 5,
                "placeholder": "Tell guests what makes your place worth staying at"
            }),

            "price_per_night": forms.NumberInput(attrs={
                "class": "input",
                "placeholder": "e.g. 450"
            }),

            "max_guests": forms.NumberInput(attrs={
                "class": "input",
            }),

            "min_nights": forms.NumberInput(attrs={
                "class": "input",
            }),

            "suburb": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Block H"
            }),

            "town": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. Soshanguve"
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
                "placeholder": "e.g. Soshanguve, Pretoria (what guests will see)"
            }),

            "full_address": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Street address for verification"
            }),

            "postal_code": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "e.g. 0152",
                "inputmode": "numeric",
            }),

            "check_in_time": forms.TimeInput(attrs={
                "class": "input",
                "type": "time",
            }),

            "check_out_time": forms.TimeInput(attrs={
                "class": "input",
                "type": "time",
            }),

            "house_rules": forms.Textarea(attrs={
                "class": "input",
                "rows": 3,
                "placeholder": "e.g. No smoking indoors, quiet after 10pm"
            }),

            "contact_phone": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "071 234 5678"
            }),

            "contact_whatsapp": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "071 234 5678"
            }),

            "contact_email": forms.EmailInput(attrs={
                "class": "input",
                "placeholder": "you@example.com"
            }),
        }

    def clean_max_guests(self):
        value = self.cleaned_data["max_guests"]
        if value < 1:
            raise forms.ValidationError("Must allow at least 1 guest.")
        return value


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["check_in", "check_out", "num_guests", "message"]

        widgets = {
            "check_in": forms.DateInput(attrs={
                "class": "input",
                "type": "date",
            }),
            "check_out": forms.DateInput(attrs={
                "class": "input",
                "type": "date",
            }),
            "num_guests": forms.NumberInput(attrs={
                "class": "input",
            }),
            "message": forms.Textarea(attrs={
                "class": "input",
                "rows": 3,
                "placeholder": "Optional - anything the host should know (arrival time, number of kids, etc.)"
            }),
        }

    def __init__(self, *args, guesthouse=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.guesthouse = guesthouse

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get("check_in")
        check_out = cleaned.get("check_out")
        num_guests = cleaned.get("num_guests")

        if check_in and check_out and check_out <= check_in:
            self.add_error("check_out", "Check-out must be after check-in.")

        if check_in and check_out and self.guesthouse:
            nights = (check_out - check_in).days
            if nights and nights < self.guesthouse.min_nights:
                self.add_error(
                    "check_out",
                    f"This host requires a minimum stay of {self.guesthouse.min_nights} night(s)."
                )

        if num_guests and self.guesthouse and num_guests > self.guesthouse.max_guests:
            self.add_error(
                "num_guests",
                f"This place sleeps a maximum of {self.guesthouse.max_guests} guests."
            )

        return cleaned
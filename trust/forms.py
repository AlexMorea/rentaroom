from django import forms

from .models import FraudReport


class FraudReportForm(forms.ModelForm):
    # Free-text room reference, kept separate from the FK so an
    # anonymous/unsure reporter can still paste a link or "the room on
    # Vosman Street" without needing to know an internal room ID.
    listing_reference = forms.CharField(
        required=False,
        label="Listing link or description (if any)",
        widget=forms.TextInput(attrs={"placeholder": "e.g. rooms4you.co.za/rooms/42/ or the address"}),
    )

    class Meta:
        model = FraudReport
        fields = ["category", "detail", "reporter_contact", "listing_reference"]
        labels = {
            "category": "What are you reporting?",
            "detail": "What happened?",
            "reporter_contact": "Your email or phone (optional, so we can follow up)",
        }
        widgets = {
            "detail": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Name of the landlord/tenant, phone or email used, dates, payment details requested...",
            }),
        }

    def save(self, *, user=None, commit=True):
        report = super().save(commit=False)
        if user is not None and user.is_authenticated:
            report.reporter = user
        listing_reference = self.cleaned_data.get("listing_reference", "").strip()
        if listing_reference:
            note = f"Listing reference provided by reporter: {listing_reference}"
            report.detail = f"{report.detail}\n\n{note}".strip()
        if commit:
            report.save()
        return report

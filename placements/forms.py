from django import forms

from .models import Placement

# Module-level (not a class attribute) on purpose: a list comprehension
# inside a class body runs in its own scope and can only see the
# enclosing module/global scope, NOT other attributes of the same class.
# Referencing a class attribute from inside a class-body comprehension
# raises NameError - this bit the original version of this file.
LANDLORD_EDITABLE_STATUSES = [
    Placement.STATUS_INTERESTED,
    Placement.STATUS_VIEWING_SCHEDULED,
    Placement.STATUS_VIEWING_COMPLETED,
    Placement.STATUS_APPROVED,
    Placement.STATUS_CANCELLED,
]


class PlacementUpdateForm(forms.ModelForm):
    """
    Used by the landlord dashboard to move a placement forward and set
    the viewing/move-in dates. Deliberately restricted to the statuses a
    landlord should be setting by hand - Moved In / Success Fee Due / Paid
    / Verification Required are all system-driven outcomes (see
    Placement.confirm_move_in / mark_success_fee_due), not something a
    landlord should be able to just click into.
    """

    status = forms.ChoiceField(
        choices=[
            (value, label) for value, label in Placement.STATUS_CHOICES
            if value in LANDLORD_EDITABLE_STATUSES
        ]
    )

    class Meta:
        model = Placement
        fields = ["status", "viewing_date", "move_in_date"]
        widgets = {
            "viewing_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "input"},
                format="%Y-%m-%dT%H:%M",
            ),
            "move_in_date": forms.DateInput(
                attrs={"type": "date", "class": "input"}
            ),
            "status": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["viewing_date"].input_formats = ["%Y-%m-%dT%H:%M"]


class MoveInConfirmationForm(forms.Form):
    """
    A deliberately tiny form: the whole "did the tenant move in" question
    boils down to one Yes/No choice from whichever side is answering.
    """
    CONFIRM_YES = "yes"
    CONFIRM_NO = "no"

    confirmed = forms.ChoiceField(
        choices=[(CONFIRM_YES, "Yes, moved in"), (CONFIRM_NO, "No, did not move in")],
        widget=forms.RadioSelect,
    )

    def confirmed_bool(self) -> bool:
        return self.cleaned_data["confirmed"] == self.CONFIRM_YES
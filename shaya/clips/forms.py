from datetime import date
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Comment, CreatorProfile, Report, Video

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".3gp", ".m4v"}


class SignUpForm(UserCreationForm):
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="You must be 13 or older. You need to be 18+ to get paid.",
    )

    class Meta:
        model = User
        fields = ["username"]

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 13:
            raise forms.ValidationError("Shaya is for people aged 13 and older.")
        return dob


class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ["file", "caption", "language", "province"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"accept": "video/*", "capture": "user"}),
            "caption": forms.Textarea(attrs={"rows": 2, "placeholder": "Say something… #mzansi"}),
        }

    def clean_file(self):
        f = self.cleaned_data["file"]
        if Path(f.name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Upload an MP4, MOV, WEBM or 3GP video.")
        if f.size > settings.SHAYA["MAX_UPLOAD_BYTES"]:
            mb = settings.SHAYA["MAX_UPLOAD_BYTES"] // (1024 * 1024)
            raise forms.ValidationError(f"Videos must be under {mb} MB.")
        return f


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text"]


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "details"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CreatorProfile
        fields = ["display_name", "bio", "province", "language", "payout_shap_id", "data_saver"]
        labels = {
            "payout_shap_id": "PayShap ShapID (e.g. 0821234567@yourbank)",
            "data_saver": "Data saver: play lighter videos and don't preload",
        }

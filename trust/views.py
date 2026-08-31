from django.contrib import messages
from django.shortcuts import redirect, render

from listings.models import Profile

from .forms import FraudReportForm
from .models import FraudReport


def _trust_stats():
    return {
        "verified_landlord_count": Profile.objects.filter(is_verified_landlord=True).count(),
        "reports_received_count": FraudReport.objects.count(),
        "reports_resolved_count": FraudReport.objects.filter(
            status__in=(FraudReport.STATUS_RESOLVED, FraudReport.STATUS_DISMISSED)
        ).count(),
    }


def trust_home(request):
    return render(request, "trust/home.html", _trust_stats())


def official_communication(request):
    return render(request, "trust/official_communication.html")


def stay_safe(request):
    return render(request, "trust/stay_safe.html")


def renting_safely(request):
    return render(request, "trust/renting_safely.html")


def verification(request):
    return render(request, "trust/verification.html")


def fraud_alerts(request):
    return render(request, "trust/fraud_alerts.html")


def report_fraud(request):
    if request.method == "POST":
        form = FraudReportForm(request.POST)
        if form.is_valid():
            report = form.save(user=request.user)
            messages.success(
                request,
                f"Report received — reference {report.reference_code}. "
                "Our Trust & Safety team will review it and may reach out "
                "if you left contact details."
            )
            return redirect("trust:report_fraud")
    else:
        form = FraudReportForm()

    return render(request, "trust/report_fraud.html", {"form": form, **_trust_stats()})

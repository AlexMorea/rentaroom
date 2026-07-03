from django.shortcuts import render


def trust_home(request):
    return render(request, "trust/home.html")


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
    return render(request, "trust/report_fraud.html")
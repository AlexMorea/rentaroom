from django.urls import path
from . import views

app_name = "trust"

urlpatterns = [
    path("", views.trust_home, name="home"),
    path("official-communication/", views.official_communication, name="official_communication"),
    path("stay-safe/", views.stay_safe, name="stay_safe"),
    path("renting-safely/", views.renting_safely, name="renting_safely"),
    path("verification/", views.verification, name="verification"),
    path("fraud-alerts/", views.fraud_alerts, name="fraud_alerts"),
    path("report-fraud/", views.report_fraud, name="report_fraud"),
]
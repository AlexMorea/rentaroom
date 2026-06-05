from django.urls import path
from . import views

app_name = "services"

urlpatterns = [

    # Guardian
    path("guardian/", views.guardian_home, name="guardian_home"),
    path("guardian/start/", views.start_guardian_session, name="start_guardian_session"),
    path("guardian/end/<int:session_id>/", views.end_guardian_session, name="end_guardian_session"),

    # AJAX
    path("guardian/ping/<int:session_id>/", views.save_location_ping, name="save_location_ping"),
    path("guardian/panic/<int:session_id>/", views.trigger_panic_alert, name="trigger_panic_alert"),

    # Bakkie
    path("bakkie/", views.bakkie_home, name="bakkie_home"),
    path("bakkie/register/", views.register_bakkie_driver, name="register_bakkie_driver"),
    path("driver/dashboard/", views.driver_dashboard, name="driver_dashboard"),
    path("driver/toggle-availability/", views.toggle_driver_availability, name="toggle_driver_availability",),
    path("driver/<int:driver_id>/", views.driver_profile, name="driver_profile",),
    path(
        "booking/create/<int:driver_id>/",
        views.create_booking,
        name="create_booking",
    ),

    path(
        "bookings/",
        views.my_bookings,
        name="my_bookings",
    ),

    path(
        "driver/bookings/",
        views.driver_bookings,
        name="driver_bookings",
    ),

    path(
        "driver-terms/",
        views.driver_terms,
        name="driver_terms"
    ),
]

from django.urls import path

from . import views

urlpatterns = [

    # Guardian4You
    path(
        "guardian/",
        views.guardian_home,
        name="guardian_home"
    ),

    path(
        "guardian/start/",
        views.start_guardian_session,
        name="start_guardian_session"
    ),

    path(
        "guardian/panic/",
        views.trigger_panic_alert,
        name="panic_alert"
    ),

    path(
        "guardian/end/<int:session_id>/",
        views.end_guardian_session,
        name="end_guardian_session"
    ),

    # Bakkie4You
    path(
        "bakkie/",
        views.bakkie_home,
        name="bakkie_home"
    ),

]
from django.urls import path

from . import views

app_name = "placements"

urlpatterns = [
    path("landlord/", views.landlord_dashboard, name="landlord_dashboard"),
    path("landlord/<int:placement_id>/update/", views.update_placement, name="update_placement"),
    path(
        "landlord/<int:placement_id>/report-unreachable/",
        views.report_tenant_unreachable,
        name="report_tenant_unreachable",
    ),
    path("tenant/", views.tenant_dashboard, name="tenant_dashboard"),
    path("<int:placement_id>/confirm-move-in/", views.confirm_move_in, name="confirm_move_in"),

    # Waitlists
    path("rooms/<int:room_id>/waitlist/join/", views.join_waitlist, name="join_waitlist"),
    path("rooms/<int:room_id>/waitlist/leave/", views.leave_waitlist, name="leave_waitlist"),
    path("landlord/rooms/<int:room_id>/waitlist/", views.room_waitlist, name="room_waitlist"),
    path("landlord/rooms/<int:room_id>/waitlist/add/", views.add_to_waitlist, name="add_to_waitlist"),
    path("landlord/waitlist/<int:entry_id>/remove/", views.remove_from_waitlist, name="remove_from_waitlist"),
]

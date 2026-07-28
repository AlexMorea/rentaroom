from django.urls import path

from . import views

app_name = "placements"

urlpatterns = [
    path("landlord/", views.landlord_dashboard, name="landlord_dashboard"),
    path("landlord/<int:placement_id>/update/", views.update_placement, name="update_placement"),
    path("tenant/", views.tenant_dashboard, name="tenant_dashboard"),
    path("<int:placement_id>/confirm-move-in/", views.confirm_move_in, name="confirm_move_in"),
]

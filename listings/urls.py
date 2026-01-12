from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("rooms/", views.room_list, name="room_list"),
    path("room/<int:pk>/", views.room_detail, name="room_detail"),
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/add/", views.create_room, name="add_room"),
    path("rooms/new/", views.create_room, name="create_room"),
    path("rooms/<int:pk>/edit/", views.edit_room, name="edit_room"),
    path("rooms/<int:pk>/delete/", views.delete_room, name="delete_room"),
    path(
        "rooms/<int:room_id>/upload-images/",
        views.upload_room_images,
        name="upload_room_images",
    ),
    path(
        "images/<int:image_id>/delete/",
        views.delete_room_image,
        name="delete_room_image",
    ),
    path("rooms/<int:pk>/images/", views.edit_room_images, name="edit_room_images"),
    path("rooms/<int:room_id>/review/", views.add_review, name="add_review"),
    path(
        "track-contact/<int:room_id>/<str:method>/",
        views.track_contact,
        name="track_contact",
    ),
    path("mark-success/<int:room_id>/", views.mark_success, name="mark_success"),
]

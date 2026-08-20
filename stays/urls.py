from django.urls import path

from . import views

app_name = "stays"

urlpatterns = [
    path("", views.guesthouse_list, name="guesthouse_list"),
    path("<int:pk>/", views.guesthouse_detail, name="guesthouse_detail"),
    path("new/", views.create_guesthouse, name="create_guesthouse"),
    path("<int:pk>/edit/", views.edit_guesthouse, name="edit_guesthouse"),
    path("<int:pk>/images/", views.upload_guesthouse_images, name="upload_guesthouse_images"),
    path("mine/", views.my_guesthouses, name="my_guesthouses"),

    path("<int:pk>/book/", views.request_booking, name="request_booking"),
    path("bookings/mine/", views.my_bookings, name="my_bookings"),
    path("bookings/host/", views.host_bookings, name="host_bookings"),
    path("bookings/<int:pk>/", views.booking_detail, name="booking_detail"),
    path("bookings/<int:pk>/accept/", views.accept_booking, name="accept_booking"),
    path("bookings/<int:pk>/decline/", views.decline_booking, name="decline_booking"),
    path("bookings/<int:pk>/cancel/", views.cancel_booking, name="cancel_booking"),
]
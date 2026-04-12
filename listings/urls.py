from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import RateLimitedPasswordResetView

urlpatterns = [
    path("", views.room_list, name="home"),
    path("rooms/", views.room_list, name="room_list"),
    path("room/<int:pk>/", views.room_detail, name="room_detail"),

    path("rooms/new/", views.create_room, name="create_room"),

    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("verify-phone/", views.verify_phone, name="verify_phone"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),
    path("verify-email/<uuid:token>/", views.verify_email, name="verify_email"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),

    # tenant save/unsave
    path("favorite/<int:room_id>/toggle/", views.toggle_favorite, name="toggle_favorite"),

    # ✅ Public legal/safety pages
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("safety/", views.safety, name="safety"),

    # ✅ Report listing (public)
    path("room/<int:pk>/report/", views.report_room, name="report_room"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/add/", views.create_room, name="add_room"),
    path("dashboard/contacts/", views.contacts_analytics, name="contacts_analytics"),

    path("landlord/rooms/", views.landlord_rooms, name="landlord_rooms"),
    path("landlord/images/", views.landlord_images_hub, name="landlord_images_hub"),

    path("rooms/<int:pk>/images/", views.edit_room_images, name="edit_room_images"),
    path("rooms/<int:pk>/edit/", views.edit_room, name="edit_room"),
    path("rooms/<int:pk>/delete/", views.delete_room, name="delete_room"),

    path("rooms/<int:room_id>/upload-images/", views.upload_room_images, name="upload_room_images"),
    path("images/<int:image_id>/delete/", views.delete_room_image, name="delete_room_image"),

    path("rooms/<int:room_id>/review/", views.add_review, name="add_review"),

    path("track-contact/<int:room_id>/<str:method>/", views.track_contact, name="track_contact"),
    path("mark-success/<int:room_id>/", views.mark_success, name="mark_success"),

    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("contact/", views.contact, name="contact"),
    path("heatmap/", views.heatmap, name="heatmap"),

    path("password-reset/", RateLimitedPasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        success_url="/password-reset/done/",
    ), name="password_reset"),

    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html"
    ), name="password_reset_done"),

    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
        success_url="/reset/done/"
    ), name="password_reset_confirm"),

    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html"
    ), name="password_reset_complete"),
]
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import RateLimitedPasswordResetView
from accounts.views import membership_view

urlpatterns = [

    
    # PUBLIC PAGES
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("contact/", views.contact, name="contact"),

    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("safety/", views.safety, name="safety"),
    path("support/", views.support, name="support"),



    # AUTH
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),

    path("verify-account/", views.verify_account, name="verify_account"),
    path("resend-account-otp/", views.resend_account_otp, name="resend_account_otp"),

    path("change-email/", views.change_email, name="change_email"),
    path("confirm-email-change/", views.confirm_email_change, name="confirm_email_change"),

    path("change-phone/", views.change_phone, name="change_phone"),
    path("confirm-phone/", views.confirm_phone_change, name="confirm_phone_change"),

    path("delete-account/", views.delete_account, name="delete_account"),


    # PASSWORD RESET
    path(
        "password-reset/",
        RateLimitedPasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            success_url="/password-reset/done/",
        ),
        name="password_reset",
    ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),

    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/reset/done/",
        ),
        name="password_reset_confirm",
    ),

    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),


    # MEMBERSHIP
    path("membership/", membership_view, name="membership"),


    # PROFILE + MESSAGING
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("inbox/", views.inbox, name="inbox"),


    # ROOMS (CORE RESOURCE)
    path("rooms/", views.room_list, name="room_list"),
    path("rooms/new/", views.create_room, name="create_room"),

    path("rooms/<int:pk>/", views.room_detail, name="room_detail"),
    path("rooms/<int:pk>/edit/", views.edit_room, name="edit_room"),
    path("rooms/<int:pk>/delete/", views.delete_room, name="delete_room"),

    # images
    path("rooms/<int:pk>/images/", views.edit_room_images, name="edit_room_images"),
    path("rooms/<int:room_id>/upload-images/", views.upload_room_images, name="upload_room_images"),
    path("images/<int:image_id>/reorder/<str:direction>/", views.reorder_room_image, name="reorder_room_image"),
    path("images/<int:image_id>/delete/", views.delete_room_image, name="delete_room_image"),

    # interactions
    path("rooms/<int:room_id>/review/", views.add_review, name="add_review"),
    path("rooms/<int:room_id>/message/", views.send_message, name="send_message"),
    path("rooms/<int:room_id>/conversation/<int:other_user_id>/", views.conversation_thread, name="conversation_thread"),

    path("rooms/<int:room_id>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("rooms/<int:room_id>/contact/<str:method>/", views.track_contact, name="track_contact"),
    path("rooms/<int:room_id>/success/", views.mark_success, name="mark_success"),

    path("rooms/<int:pk>/report/", views.report_room, name="report_room"),


    # LANDLORD DASHBOARD
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/contacts/", views.contacts_analytics, name="contacts_analytics"),

    path("landlord/rooms/", views.landlord_rooms, name="landlord_rooms"),
    path("landlord/rooms/<int:room_id>/toggle-vacancy/", views.toggle_room_vacancy, name="toggle_room_vacancy"),
    path("landlord/<int:user_id>/profile/", views.landlord_profile, name="landlord_profile"),
    path("landlord/images/", views.landlord_images_hub, name="landlord_images_hub"),

    # PWA
    path("offline/", views.offline_page, name="offline"),
]
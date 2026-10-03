from django.urls import path

from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("about/", views.about, name="about"),
    path("signup/", views.signup, name="signup"),
    path("upload/", views.upload, name="upload"),
    path("studio/", views.dashboard, name="dashboard"),
    path("studio/withdraw/", views.withdraw, name="withdraw"),
    path("settings/", views.edit_profile, name="edit_profile"),
    path("data-saver/", views.toggle_data_saver, name="toggle_data_saver"),
    path("v/<int:pk>/", views.video_detail, name="video_detail"),
    path("v/<int:pk>/view/", views.view_beacon, name="view_beacon"),
    path("v/<int:pk>/like/", views.toggle_like, name="toggle_like"),
    path("v/<int:pk>/comment/", views.add_comment, name="add_comment"),
    path("v/<int:pk>/report/", views.report_video, name="report_video"),
    path("ad/<int:pk>/impression/", views.ad_impression, name="ad_impression"),
    path("@<str:username>/", views.profile, name="profile"),
    path("@<str:username>/follow/", views.toggle_follow, name="toggle_follow"),
]

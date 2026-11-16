from django.urls import path

from . import push_views
from .views import membership_view

urlpatterns = [
    path("membership/", membership_view, name="membership"),

    path("push/subscribe/", push_views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", push_views.push_unsubscribe, name="push_unsubscribe"),
]

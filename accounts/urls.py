from django.urls import path

from . import push_views, views
from .views import membership_view

urlpatterns = [
    path("membership/", membership_view, name="membership"),
    path("membership/<str:tier>/", views.membership_payment_view, name="membership_payment"),
    path("admin/memberships/", views.admin_membership_dashboard, name="admin_membership_dashboard"),
    path("admin/memberships/<int:pk>/approve/", views.approve_membership, name="approve_membership"),
    path("admin/memberships/<int:pk>/reject/", views.reject_membership, name="reject_membership"),

    path("push/subscribe/", push_views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", push_views.push_unsubscribe, name="push_unsubscribe"),
]

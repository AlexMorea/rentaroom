from django.urls import path
from .views import membership_view

urlpatterns = [
    path("membership/", membership_view, name="membership"),
]
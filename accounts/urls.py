from django.urls import path
from . import views
from .views import membership_view

urlpatterns = [
    path("membership/", membership_view, name="membership"),
    path("membership/<str:tier>/", views.membership_payment_view, name="membership_payment"),
]
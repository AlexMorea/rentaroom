from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("pro/checkout/", views.pro_checkout, name="pro_checkout"),
    path("pro/cancel/", views.cancel_pro, name="cancel_pro"),
    path("rooms/<int:room_id>/boost/", views.boost_room, name="boost_room"),
    path("payments/<int:payment_id>/return/", views.payment_return, name="payment_return"),
    path("payments/<int:payment_id>/cancelled/", views.payment_cancelled, name="payment_cancelled"),
    path("payfast/notify/", views.payfast_notify, name="payfast_notify"),
]

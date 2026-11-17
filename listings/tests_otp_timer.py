from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from listings.models import PhoneOTP
from listings.views.auth_views import DEVICE_OTP_PURPOSE


class OtpTimerTests(TestCase):
    """The verify pages render server-computed countdowns."""

    def setUp(self):
        self.user = User.objects.create_user("otp@example.com", "otp@example.com", "x", is_active=False)

    def make_code(self, seconds_old, purpose="email_verification"):
        otp = PhoneOTP.objects.create(user=self.user, phone_number=purpose, otp="123456")
        PhoneOTP.objects.filter(pk=otp.pk).update(created_at=timezone.now() - timedelta(seconds=seconds_old))

    def test_fresh_code_shows_full_timers(self):
        self.make_code(5)
        session = self.client.session
        session["pending_user_id"] = self.user.id
        session.save()
        resp = self.client.get(reverse("verify_account"))
        self.assertGreaterEqual(resp.context["otp_expires_in"], 890)
        self.assertGreaterEqual(resp.context["otp_resend_in"], 80)
        self.assertContains(resp, "data-otp-timer")
        self.assertContains(resp, "otp-timer")

    def test_old_code_is_expired_and_resend_open(self):
        self.make_code(20 * 60)
        session = self.client.session
        session["pending_user_id"] = self.user.id
        session.save()
        resp = self.client.get(reverse("verify_account"))
        self.assertEqual(resp.context["otp_expires_in"], 0)
        self.assertEqual(resp.context["otp_resend_in"], 0)

    def test_device_page_uses_device_code(self):
        self.user.is_active = True
        self.user.save()
        self.make_code(120, purpose=DEVICE_OTP_PURPOSE)
        session = self.client.session
        session["pending_device_user_id"] = self.user.id
        session.save()
        resp = self.client.get(reverse("verify_device"))
        self.assertTrue(770 <= resp.context["otp_expires_in"] <= 780)
        self.assertEqual(resp.context["otp_resend_in"], 0)

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


class EmailChangeTests(TestCase):
    """The code goes to the NEW address, the confirm page renders, and
    the old address is told once the change is made."""

    def setUp(self):
        from listings.models import Profile

        self.user = User.objects.create_user("old@example.com", "old@example.com", "x")
        Profile.objects.filter(user=self.user).update(role="tenant")
        self.client.force_login(self.user)

    def test_full_change(self):
        from django.core import mail

        resp = self.client.post(reverse("change_email"), {"email": "new@example.com"})
        self.assertRedirects(resp, reverse("confirm_email_change"))
        self.assertEqual(mail.outbox[-1].to, ["new@example.com"])

        page = self.client.get(reverse("confirm_email_change"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "new@example.com")

        code = PhoneOTP.objects.get(user=self.user, phone_number="email_change").otp
        self.client.post(reverse("confirm_email_change"), {"otp": code})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(mail.outbox[-1].to, ["old@example.com"])
        self.assertIn("was changed", mail.outbox[-1].subject)

    def test_wrong_code_changes_nothing(self):
        self.client.post(reverse("change_email"), {"email": "new@example.com"})
        self.client.post(reverse("confirm_email_change"), {"otp": "000000"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase

from accounts.devices import DEVICE_COOKIE_NAME
from accounts.models import TrustedDevice
from listings.models import PhoneOTP, Profile


class NewDeviceLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="device_user",
            email="device_user@example.com",
            password="password123",
        )
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.is_phone_verified = True
        profile.save()

    def tearDown(self):
        cache.clear()

    def _login(self):
        return self.client.post(
            "/login/",
            {"email": self.user.email, "password": "password123"},
        )

    def test_unrecognised_device_is_challenged_not_logged_in(self):
        resp = self._login()

        # Not logged in yet - redirected to the device challenge instead.
        self.assertFalse(self.client.session.get("_auth_user_id"))
        self.assertRedirects(resp, "/verify-device/")
        self.assertEqual(
            self.client.session.get("pending_device_user_id"), self.user.id
        )
        self.assertTrue(
            PhoneOTP.objects.filter(user=self.user, phone_number="device_verification").exists()
        )

    def test_correct_code_completes_login_and_sets_device_cookie(self):
        self._login()

        otp = PhoneOTP.objects.get(user=self.user, phone_number="device_verification").otp

        resp = self.client.post("/verify-device/", {"otp": otp})

        self.assertTrue(self.client.session.get("_auth_user_id"))
        self.assertIn(DEVICE_COOKIE_NAME, resp.cookies)
        self.assertTrue(TrustedDevice.objects.filter(user=self.user).exists())

    def test_wrong_code_does_not_log_in(self):
        self._login()

        resp = self.client.post("/verify-device/", {"otp": "000000"})

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_known_device_skips_challenge(self):
        # First login completes the challenge and gets a device cookie.
        self._login()
        otp = PhoneOTP.objects.get(user=self.user, phone_number="device_verification").otp
        self.client.post("/verify-device/", {"otp": otp})
        self.client.post("/logout/")

        # Second login from the same client (same cookie jar) should not
        # be challenged again.
        self._login()
        self.assertTrue(self.client.session.get("_auth_user_id"))
        self.assertNotIn("pending_device_user_id", self.client.session)


class SmoothDeviceTrustTests(TestCase):
    """Remembered devices shouldn't nag: several accounts can share a
    browser, trust slides with use, and only password changes, removal
    or 90 days of disuse end it."""

    def setUp(self):
        self.client = Client()
        self.users = []
        for name in ("landlord_a", "tenant_b"):
            user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password123")
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.is_phone_verified = True
            profile.save()
            self.users.append(user)

    def tearDown(self):
        cache.clear()

    def _login(self, user):
        return self.client.post("/login/", {"email": user.email, "password": "password123"})

    def _verify(self, user):
        self._login(user)
        otp = PhoneOTP.objects.get(user=user, phone_number="device_verification").otp
        return self.client.post("/verify-device/", {"otp": otp})

    def _is_challenged(self, user):
        self.client.post("/logout/")
        self._login(user)
        challenged = "pending_device_user_id" in self.client.session
        self.client.post("/logout/")
        return challenged

    def test_two_accounts_on_one_browser_both_stay_trusted(self):
        a, b = self.users
        self._verify(a)
        self.client.post("/logout/")
        self._verify(b)

        self.assertFalse(self._is_challenged(a))
        self.assertFalse(self._is_challenged(b))
        self.assertFalse(self._is_challenged(a))
        # One browser, one entry per account - no duplicates piling up.
        self.assertEqual(TrustedDevice.objects.filter(user=a).count(), 1)

    def test_signing_in_on_a_known_device_refreshes_its_cookie(self):
        a = self.users[0]
        self._verify(a)
        self.client.post("/logout/")
        resp = self._login(a)
        self.assertIn(DEVICE_COOKIE_NAME, resp.cookies)
        self.assertGreater(int(resp.cookies[DEVICE_COOKIE_NAME]["max-age"]), 0)

    def test_device_unused_for_90_days_confirms_again(self):
        from datetime import timedelta

        from django.utils import timezone

        a = self.users[0]
        self._verify(a)
        TrustedDevice.objects.filter(user=a).update(last_seen_at=timezone.now() - timedelta(days=91))
        self.assertTrue(self._is_challenged(a))

    def test_password_change_keeps_this_device_and_ends_others(self):
        a = self.users[0]
        TrustedDevice.objects.create(user=a, token_hash="0" * 64, label="old phone")
        self._verify(a)
        self.client.post("/settings/password/", {
            "old_password": "password123", "new_password1": "Blue7Taxi!Rain2", "new_password2": "Blue7Taxi!Rain2",
        })
        labels = list(TrustedDevice.objects.filter(user=a).values_list("label", flat=True))
        self.assertNotIn("old phone", labels)
        self.assertEqual(len(labels), 1)

    def test_password_reset_ends_all_device_trust(self):
        from listings.forms import ResetPasswordForm

        a = self.users[0]
        self._verify(a)
        form = ResetPasswordForm(a, {"new_password1": "Blue7Taxi!Rain2", "new_password2": "Blue7Taxi!Rain2"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertFalse(TrustedDevice.objects.filter(user=a).exists())

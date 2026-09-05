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

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase

from listings.models import PhoneOTP, Profile


class FullOTPFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="full_otp_user",
            email="full_otp@example.com",
            password="password123",
            is_active=False,
        )
        # ensure profile exists
        Profile.objects.get_or_create(user=self.user)

    def tearDown(self):
        cache.clear()

    def test_verify_successful_flow(self):
        # create OTP record
        otp_value = "123456"
        PhoneOTP.objects.filter(user=self.user).delete()
        PhoneOTP.objects.create(user=self.user, phone_number="email_verification", otp=otp_value)

        # set pending session
        session = self.client.session
        session["pending_user_id"] = self.user.id
        session.save()

        # POST correct OTP
        resp = self.client.post("/verify-account/", {"otp": otp_value})

        # should redirect on success
        self.assertIn(resp.status_code, (302, 301))

        # refresh from DB
        self.user.refresh_from_db()
        profile = self.user.profile
        self.assertTrue(profile.is_email_verified)
        self.assertTrue(profile.is_phone_verified)
        self.assertTrue(self.user.is_active)

        # session should no longer have pending_user_id
        self.assertNotIn("pending_user_id", self.client.session)

    def test_too_many_attempts_blocks(self):
        # prime attempts to threshold
        key = f"otp_attempts_{self.user.id}"
        cache.set(key, 5, timeout=900)

        session = self.client.session
        session["pending_user_id"] = self.user.id
        session.save()

        resp = self.client.post("/verify-account/", {"otp": "000000"})

        # view should render page with error (200) and not log user in
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_resend_without_session_returns_400(self):
        # ensure no pending id in session
        if "pending_user_id" in self.client.session:
            del self.client.session["pending_user_id"]
            self.client.session.save()

        resp = self.client.get("/resend-account-otp/")
        self.assertEqual(resp.status_code, 400)

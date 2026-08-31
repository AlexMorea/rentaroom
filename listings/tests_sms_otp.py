"""
SMS OTP (Twilio Verify) wiring tests.

These never touch the network - the twilio-facing functions in
``listings.services.sms`` are patched. They check that the view layer
picks the SMS channel when it's enabled, verifies against Twilio, and
falls back to email OTP when Twilio is unavailable.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings

from listings.models import PhoneOTP
from listings.services import sms

REGISTER_POST = {
    "first_name": "Test",
    "last_name": "Tenant",
    "email": "sms_tenant@example.com",
    "role": "tenant",
    "persona": "worker",
    "country_code": "+27",
    "phone_number": "0821234567",
    "terms_accepted": "on",
    "password1": "sTr0ng-pass-9271",
    "password2": "sTr0ng-pass-9271",
}


class SMSServiceGuardTests(TestCase):
    def test_start_verification_raises_when_disabled(self):
        with self.assertRaises(sms.SMSNotConfigured):
            sms.start_verification("+27821234567")

    def test_check_verification_returns_false_when_disabled(self):
        with self.assertRaises(sms.SMSNotConfigured):
            sms.check_verification("+27821234567", "123456")


@override_settings(
    SMS_OTP_ENABLED=True,
    TWILIO_ACCOUNT_SID="AC_test",
    TWILIO_AUTH_TOKEN="tok_test",
    TWILIO_VERIFY_SERVICE_SID="VA_test",
)
class SMSRegistrationFlowTests(TestCase):
    def tearDown(self):
        cache.clear()

    @patch("listings.views.auth_views.start_verification", return_value=True)
    def test_register_uses_sms_channel(self, mock_start):
        resp = self.client.post("/register/", REGISTER_POST)
        self.assertEqual(resp.status_code, 302)

        mock_start.assert_called_once()
        # sent to the E.164 form of the number they typed
        self.assertEqual(mock_start.call_args[0][0], "+27821234567")

        self.assertEqual(self.client.session["otp_channel"], "sms")

        user = User.objects.get(email="sms_tenant@example.com")
        # Verify owns the code - we don't store a PhoneOTP row for SMS
        self.assertFalse(PhoneOTP.objects.filter(user=user).exists())

    @patch("listings.views.auth_views.check_verification", return_value=True)
    @patch("listings.views.auth_views.start_verification", return_value=True)
    def test_verify_account_checks_against_twilio(self, mock_start, mock_check):
        self.client.post("/register/", REGISTER_POST)
        user = User.objects.get(email="sms_tenant@example.com")

        resp = self.client.post("/verify-account/", {"otp": "123456"})
        self.assertEqual(resp.status_code, 302)

        mock_check.assert_called_once_with("+27821234567", "123456")

        user.refresh_from_db()
        self.assertTrue(user.profile.is_phone_verified)
        self.assertTrue(user.profile.is_email_verified)
        self.assertTrue(user.is_active)
        self.assertNotIn("pending_user_id", self.client.session)

    @patch(
        "listings.views.auth_views.start_verification",
        side_effect=sms.SMSSendError("boom"),
    )
    def test_register_falls_back_to_email_when_sms_fails(self, mock_start):
        resp = self.client.post("/register/", REGISTER_POST)
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(self.client.session["otp_channel"], "email")

        user = User.objects.get(email="sms_tenant@example.com")
        self.assertTrue(PhoneOTP.objects.filter(user=user, is_verified=False).exists())

from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from listings.models import Profile
from utils.whatsapp import send_whatsapp_template, whatsapp_enabled

WHATSAPP_TEST_SETTINGS = {
    "WHATSAPP_ACCESS_TOKEN": "test-token",
    "WHATSAPP_PHONE_NUMBER_ID": "123456789",
}


class WhatsappEnabledTests(TestCase):
    def test_disabled_by_default(self):
        # Tests (and any deploy without real Meta credentials) should
        # never accidentally think WhatsApp is live.
        self.assertFalse(whatsapp_enabled())

    @override_settings(**WHATSAPP_TEST_SETTINGS)
    def test_enabled_once_both_env_vars_are_set(self):
        self.assertTrue(whatsapp_enabled())

    @override_settings(WHATSAPP_ACCESS_TOKEN="token-only", WHATSAPP_PHONE_NUMBER_ID="")
    def test_disabled_if_only_one_var_is_set(self):
        self.assertFalse(whatsapp_enabled())


class SendWhatsappTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wa_user", password="p")
        self.profile = self.user.profile
        self.profile.country_code = "+27"
        self.profile.phone_number = "821234567"
        self.profile.save()

    @patch("utils.whatsapp.requests.post")
    def test_noop_when_not_configured(self, mock_post):
        sent = send_whatsapp_template(self.profile, "account_otp", params=["123456"])

        self.assertFalse(sent)
        mock_post.assert_not_called()

    @override_settings(**WHATSAPP_TEST_SETTINGS)
    @patch("utils.whatsapp.requests.post")
    def test_sends_to_the_profiles_number_with_correct_payload(self, mock_post):
        mock_post.return_value = Mock(status_code=200)

        sent = send_whatsapp_template(self.profile, "account_otp", params=["654321"])

        self.assertTrue(sent)
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        self.assertIn("123456789/messages", _args[0])
        self.assertEqual(kwargs["json"]["to"], "27821234567")
        self.assertEqual(kwargs["json"]["template"]["name"], "account_otp")
        self.assertEqual(
            kwargs["json"]["template"]["components"][0]["parameters"][0]["text"], "654321"
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")

    @override_settings(**WHATSAPP_TEST_SETTINGS)
    @patch("utils.whatsapp.requests.post")
    def test_prefers_whatsapp_number_over_phone_number(self, mock_post):
        mock_post.return_value = Mock(status_code=200)
        self.profile.whatsapp_number = "731112222"
        self.profile.save()

        send_whatsapp_template(self.profile, "account_otp", params=["1"])

        _args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["to"], "27731112222")

    @override_settings(**WHATSAPP_TEST_SETTINGS)
    @patch("utils.whatsapp.requests.post")
    def test_returns_false_and_never_raises_on_a_bad_response(self, mock_post):
        mock_post.return_value = Mock(status_code=400, text="template not approved")

        sent = send_whatsapp_template(self.profile, "account_otp", params=["1"])

        self.assertFalse(sent)

    @override_settings(**WHATSAPP_TEST_SETTINGS)
    @patch("utils.whatsapp.requests.post", side_effect=requests.ConnectionError("boom"))
    def test_returns_false_and_never_raises_on_a_network_error(self, mock_post):
        sent = send_whatsapp_template(self.profile, "account_otp", params=["1"])

        self.assertFalse(sent)

    @override_settings(**WHATSAPP_TEST_SETTINGS)
    @patch("utils.whatsapp.requests.post")
    def test_noop_with_no_phone_number_on_file(self, mock_post):
        self.profile.phone_number = ""
        self.profile.whatsapp_number = ""
        self.profile.save()

        sent = send_whatsapp_template(self.profile, "account_otp", params=["1"])

        self.assertFalse(sent)
        mock_post.assert_not_called()


class ProfileWhatsappFullNumberTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wa_profile", password="p")
        self.profile = self.user.profile
        self.profile.country_code = "+27"

    def test_falls_back_to_phone_number_when_whatsapp_number_blank(self):
        self.profile.phone_number = "821234567"
        self.assertEqual(self.profile.whatsapp_full_number(), "+27821234567")

    def test_prefers_whatsapp_number_when_set(self):
        self.profile.phone_number = "821234567"
        self.profile.whatsapp_number = "731112222"
        self.assertEqual(self.profile.whatsapp_full_number(), "+27731112222")

    def test_blank_when_neither_is_set(self):
        self.profile.phone_number = ""
        self.profile.whatsapp_number = ""
        self.assertEqual(self.profile.whatsapp_full_number(), "")


class RegistrationWhatsappOtpTests(TestCase):
    @override_settings(**WHATSAPP_TEST_SETTINGS)
    @patch("listings.utils.send_whatsapp_template")
    def test_register_sends_otp_over_whatsapp_alongside_email(self, mock_send):
        resp = self.client.post(reverse("register"), {
            "first_name": "Sam",
            "last_name": "Tenant",
            "email": "sam.tenant@example.com",
            "role": "tenant",
            "persona": "worker",
            "country_code": "+27",
            "phone_number": "0821234567",
            "terms_accepted": True,
            "password1": "SuperSecret123!",
            "password2": "SuperSecret123!",
        })

        self.assertEqual(resp.status_code, 302)
        mock_send.assert_called_once()
        profile_arg, template_arg = mock_send.call_args.args
        self.assertEqual(template_arg, "account_otp")
        self.assertEqual(profile_arg.user.email, "sam.tenant@example.com")


class VerifyAccountWhatsappWelcomeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="wa_verify@example.com", email="wa_verify@example.com", password="p"
        )
        Profile.objects.filter(user=self.user).update(role="tenant")

        from listings.models import PhoneOTP
        self.otp = PhoneOTP.objects.create(user=self.user, phone_number="", otp="111111")

        session = self.client.session
        session["pending_user_id"] = self.user.id
        session.save()

    @override_settings(**WHATSAPP_TEST_SETTINGS)
    @patch("listings.utils.send_whatsapp_template")
    def test_verifying_account_sends_welcome_over_whatsapp(self, mock_send):
        resp = self.client.post(reverse("verify_account"), {"otp": "111111"})

        self.assertEqual(resp.status_code, 302)
        mock_send.assert_called_once()
        profile_arg, template_arg = mock_send.call_args.args
        self.assertEqual(template_arg, "welcome")
        self.assertEqual(profile_arg.user_id, self.user.id)

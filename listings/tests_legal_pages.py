from django.test import TestCase, override_settings
from django.urls import reverse


class LegalPagesTests(TestCase):
    """Terms / Privacy / Pricing & Refunds / Contact carry the
    disclosures PayFast and ECTA s43 expect, without placeholders."""

    def test_pages_load(self):
        for name in ("terms", "privacy", "pricing_refunds", "contact"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_pricing_page_shows_real_prices_and_policies(self):
        body = self.client.get(reverse("pricing_refunds")).content.decode()
        for text in ("R99", "R199", "R349", "R990", "R29", "R79", "PayFast",
                     "never sees or stores your card details", "Cancelling", "Refunds",
                     "charged in error", "Featured"):
            self.assertIn(text, body)

    def test_company_details_hidden_until_set(self):
        body = self.client.get(reverse("terms")).content.decode()
        self.assertIn("4You (Pty) Ltd", body)
        self.assertNotIn("Registration number", body)
        self.assertNotIn("VAT number", body)

    @override_settings(
        COMPANY_REG_NUMBER="2025/123456/07",
        COMPANY_VAT_NUMBER="4123456789",
        COMPANY_ADDRESS="1 Example Street, Pretoria, 0001",
        COMPANY_PHONE="012 345 6789",
    )
    def test_company_details_shown_everywhere_once_set(self):
        for name in ("terms", "pricing_refunds", "contact"):
            body = self.client.get(reverse(name)).content.decode()
            for text in ("2025/123456/07", "4123456789", "1 Example Street", "012 345 6789"):
                self.assertIn(text, body, f"{text} missing on {name}")
        footer = self.client.get(reverse("home")).content.decode()
        self.assertIn("Reg. no. 2025/123456/07", footer)
        self.assertIn("including VAT", self.client.get(reverse("pricing_refunds")).content.decode())

    def test_footer_links_pricing_and_refunds(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn(reverse("pricing_refunds"), body)
        self.assertIn("Secure payments by PayFast", body)


@override_settings(
    PAYFAST_MERCHANT_ID="10000100", PAYFAST_MERCHANT_KEY="k", PAYFAST_PASSPHRASE="p",
    FOUNDING_LANDLORD_SIGNUP_DEADLINE=__import__("datetime").date(2020, 1, 1),
)
class PayConsentTests(TestCase):
    def test_plans_page_shows_consent_next_to_pay_buttons(self):
        from django.contrib.auth.models import User

        from listings.models import Profile

        user = User.objects.create_user("consent@example.com", "consent@example.com", "x")
        Profile.objects.filter(user=user).update(role="landlord")
        self.client.force_login(user)
        body = self.client.get(reverse("membership")).content.decode()
        self.assertIn("Go Pro", body)
        self.assertIn("By paying you agree", body)
        self.assertIn(reverse("pricing_refunds"), body)


class TimezoneTests(TestCase):
    def test_site_runs_on_south_african_time(self):
        from datetime import datetime, timezone as dt_tz

        from django.conf import settings
        from django.template import Context, Template
        from django.utils import timezone

        self.assertEqual(settings.TIME_ZONE, "Africa/Johannesburg")
        self.assertTrue(settings.USE_TZ)
        # 22:30 UTC is 00:30 the next day in South Africa.
        moment = datetime(2026, 11, 17, 22, 30, tzinfo=dt_tz.utc)
        self.assertEqual(Template('{{ m|date:"j M H:i" }}').render(Context({"m": moment})), "18 Nov 00:30")
        self.assertEqual(timezone.localtime(moment).date().day, 18)

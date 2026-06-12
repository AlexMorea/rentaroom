from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone


class ResendOTPTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="otp_user",
            email="otp@example.com",
            password="password123",
            is_active=False,
        )
        # ensure profile exists
        self.user.profile
        # place pending id in session
        session = self.client.session
        session["pending_user_id"] = self.user.id
        session.save()

    def tearDown(self):
        cache.clear()

    def test_resend_success_and_rate_limit(self):
        url = "/resend-account-otp/"

        # first call should succeed (200) and return cooldown
        resp1 = self.client.get(url)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertIn("cooldown", data1)
        self.assertIn("message", data1)

        # second immediate call should be rate-limited (429)
        resp2 = self.client.get(url)
        self.assertEqual(resp2.status_code, 429)
        data2 = resp2.json()
        self.assertIn("cooldown", data2)
        self.assertIn("message", data2)

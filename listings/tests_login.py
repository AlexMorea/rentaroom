from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class LoginRoleRoutingTests(TestCase):
    """
    Covers post-login redirect routing per role. Regression coverage for a bug
    where role="driver" logins raised NoReverseMatch (redirect("services:bakkie/driver_dashboard"),
    an invalid URL name) instead of reaching the driver dashboard/onboarding page.
    """

    def setUp(self):
        self.client = Client()

    def _make_verified_user(self, username, email, role):
        user = User.objects.create_user(username=username, email=email, password="password123")
        profile = user.profile
        profile.role = role
        profile.is_phone_verified = True
        profile.is_email_verified = True
        profile.save()
        return user

    def test_tenant_login_redirects_to_room_list(self):
        self._make_verified_user("tenant_login", "tenant_login@example.com", "tenant")
        resp = self.client.post(
            "/login/",
            {"email": "tenant_login@example.com", "password": "password123"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/rooms/", resp.url)

    def test_landlord_login_redirects_to_dashboard(self):
        self._make_verified_user("landlord_login", "landlord_login@example.com", "landlord")
        resp = self.client.post(
            "/login/",
            {"email": "landlord_login@example.com", "password": "password123"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_driver_login_does_not_crash(self):
        self._make_verified_user("driver_login", "driver_login@example.com", "driver")
        resp = self.client.post(
            "/login/",
            {"email": "driver_login@example.com", "password": "password123"},
        )
        # Must redirect (not raise NoReverseMatch / 500) regardless of BakkieDriver
        # verification state.
        self.assertEqual(resp.status_code, 302)

    def test_invalid_credentials_do_not_crash(self):
        resp = self.client.post(
            "/login/",
            {"email": "nobody@example.com", "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 302)


class ProfilePageRoleDisplayTests(TestCase):
    """
    Regression coverage for a bug where the generic /profile/ page labelled
    every non-tenant role "Landlord" and showed landlord-only stat links
    (Rooms/Images/Contacts) even to drivers.
    """

    def setUp(self):
        self.client = Client()

    def test_driver_profile_does_not_show_landlord_badge_or_links(self):
        user = User.objects.create_user(
            username="driver_profile", email="driver_profile@example.com", password="password123"
        )
        profile = user.profile
        profile.role = "driver"
        profile.save()

        self.client.force_login(user)
        resp = self.client.get(reverse("profile"))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["badge_text"], "Driver")
        self.assertEqual(resp.context["stat_links"], [])

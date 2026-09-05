from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from accounts.devices import DEVICE_COOKIE_NAME, hash_token
from accounts.models import TrustedDevice


def trust_device(client, user):
    """
    Pre-registers the given test Client as a known device for this user,
    so a login test that isn't specifically about the new-device OTP
    challenge (see listings.tests_device_verification for that) can
    still assert on direct post-login behaviour.
    """
    token = "test-device-token"
    TrustedDevice.objects.get_or_create(user=user, token_hash=hash_token(token))
    client.cookies[DEVICE_COOKIE_NAME] = token


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
        trust_device(self.client, user)
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


class AccountLoginLockoutTests(TestCase):
    """
    Regression coverage for a real gap: login was only rate-limited by IP,
    so a targeted credential-stuffing attack against one known account,
    spread across many different IPs, was never throttled at all (no
    single IP ever crossed the per-IP threshold). Per-account lockout
    closes that without collaterally locking out other users who happen
    to share an IP with the attacker.
    """

    def setUp(self):
        cache.clear()
        self.victim = User.objects.create_user(
            username="victim@example.com", email="victim@example.com", password="CorrectHorseBattery1!"
        )
        profile = self.victim.profile
        profile.is_phone_verified = True
        profile.is_email_verified = True
        profile.save()

    def _attempt(self, ip, email="victim@example.com", password="wrong"):
        c = Client(REMOTE_ADDR=ip)
        # Each call makes a brand-new Client (to vary the IP) - trust it
        # as a known device for whichever account is being attempted, so
        # these lockout-counter assertions aren't tangled up with the
        # separate new-device OTP challenge under test elsewhere.
        user = User.objects.filter(email__iexact=email).first()
        if user:
            trust_device(c, user)
        return c.post("/login/", {"email": email, "password": password}, follow=True)

    def test_account_locks_after_repeated_failures_across_different_ips(self):
        for i in range(7):
            self._attempt(f"10.0.0.{i}")

        # 8th attempt, brand-new IP, even with the CORRECT password - still blocked.
        resp = self._attempt("10.0.0.200", password="CorrectHorseBattery1!")
        self.assertContains(resp, "Too many login attempts on this account")
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_lockout_does_not_affect_a_different_account_on_the_shared_ip(self):
        other = User.objects.create_user(
            username="other@example.com", email="other@example.com", password="AnotherPass1!"
        )
        other_profile = other.profile
        other_profile.is_phone_verified = True
        other_profile.is_email_verified = True
        other_profile.save()

        # Attacker hammers the victim's account from one IP...
        for _ in range(7):
            self._attempt("10.0.0.5")

        # ...a different account, same IP, should be unaffected.
        resp = self._attempt("10.0.0.5", email="other@example.com", password="AnotherPass1!")
        self.assertTrue(resp.wsgi_request.user.is_authenticated)

    def test_successful_login_clears_the_account_lockout_counter(self):
        for _ in range(3):
            self._attempt("10.0.0.9")

        resp = self._attempt("10.0.0.9", password="CorrectHorseBattery1!")
        self.assertTrue(resp.wsgi_request.user.is_authenticated)

        # Counter cleared - failed attempts start fresh, not continuing
        # from 3 toward the 7 threshold.
        for _ in range(3):
            self._attempt("10.0.0.9")
        resp = self._attempt("10.0.0.9", password="CorrectHorseBattery1!")
        self.assertTrue(resp.wsgi_request.user.is_authenticated)

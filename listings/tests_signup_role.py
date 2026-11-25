from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from accounts.models import Membership
from listings.forms import ROLE_REQUIRED_MESSAGE
from listings.models import Profile


class SignupRoleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_signup_without_choosing_a_role_is_rejected(self):
        resp = self.client.post(reverse("register"), {
            "first_name": "Thandi", "last_name": "M", "email": "thandi@example.com",
            "country_code": "+27", "phone_number": "0821234567",
            "persona": "worker", "terms_accepted": "on",
            "password1": "Blue7Taxi!Rain", "password2": "Blue7Taxi!Rain",
        })

        self.assertContains(resp, escape(ROLE_REQUIRED_MESSAGE))
        self.assertFalse(User.objects.filter(email="thandi@example.com").exists())

    def test_no_role_is_preselected(self):
        resp = self.client.get(reverse("register"))

        self.assertContains(resp, '<option value="" selected>Choose one</option>', html=True)

    def test_role_link_preselects_landlord(self):
        resp = self.client.get(reverse("register") + "?role=landlord")

        self.assertContains(resp, '<option value="landlord" selected>Landlord</option>', html=True)
        self.assertEqual(self.client.session["signup_role_hint"], "landlord")


class BecomeLandlordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="t@example.com", email="t@example.com", password="pw123456!")
        Profile.objects.filter(user=self.user).update(role="tenant", is_email_verified=True, is_phone_verified=True)
        self.client.force_login(self.user)

    def test_tenant_trying_to_list_is_offered_the_switch(self):
        resp = self.client.get(reverse("create_room"))

        self.assertRedirects(resp, reverse("become_landlord"), fetch_redirect_response=False)

    def test_switching_makes_a_landlord_with_membership(self):
        resp = self.client.post(reverse("become_landlord"), {
            "home_address": "12 Tsamaya Road, Mamelodi East",
            "postal_code": "0122",
            "terms_accepted": "on",
        })

        self.assertRedirects(resp, reverse("create_room"), fetch_redirect_response=False)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.role, "landlord")
        self.assertEqual(profile.postal_code, "0122")
        self.assertTrue(profile.terms_accepted)
        self.assertTrue(Membership.objects.filter(user=self.user).exists())

    def test_switch_needs_a_real_address_and_consent(self):
        resp = self.client.post(reverse("become_landlord"), {"home_address": "Mamelodi", "postal_code": "0122"})

        self.assertContains(resp, "Please add a bit more detail to your address")
        self.assertContains(resp, "You must accept the Terms of Service")
        self.assertEqual(Profile.objects.get(user=self.user).role, "tenant")

    def test_landlord_is_sent_straight_to_listing(self):
        Profile.objects.filter(user=self.user).update(role="landlord")

        resp = self.client.get(reverse("become_landlord"))

        self.assertRedirects(resp, reverse("create_room"), fetch_redirect_response=False)

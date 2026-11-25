"""
The support WhatsApp button vs. contacting a landlord: support chats are
tagged with where they started, room pages keep the landlord's WhatsApp
as the only green button, and logged-out visitors are told plainly that a
free account unlocks the landlord's contacts.
"""
from urllib.parse import quote

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from listings.models import PhoneOTP, Profile, Room
from listings.templatetags.support_tags import support_source_label

PASSWORD = "Blue7Taxi!Rain"


def make_room():
    landlord = User.objects.create_user("sipho@example.com", "sipho@example.com", PASSWORD, first_name="Sipho")
    Profile.objects.filter(user=landlord).update(role="landlord", is_phone_verified=True, is_email_verified=True)
    return Room.objects.create(
        owner=landlord, title="Spacious Single Room in Mamelodi East", description="Clean room.", price=1300,
        location="Mamelodi East, Pretoria", suburb="Mamelodi East", town="Mamelodi", city="Pretoria",
        full_address="12 Tsamaya Ave", postal_code="0122", room_type="Single Room", contact_phone="+27821234567",
    )


def make_tenant():
    tenant = User.objects.create_user("lerato@example.com", "lerato@example.com", PASSWORD)
    Profile.objects.filter(user=tenant).update(role="tenant", is_phone_verified=True, is_email_verified=True)
    return tenant


class SupportLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.room = make_room()

    def _request(self, path):
        request = RequestFactory().get(path)
        request.resolver_match = resolve(path)
        return request

    def test_label_names_the_page_or_room(self):
        self.assertEqual(support_source_label(self._request("/rooms/")), "Browse rooms")
        self.assertEqual(
            support_source_label(self._request(f"/rooms/{self.room.id}/"), self.room),
            f"Room #{self.room.id}: Spacious Single Room in Mamelodi East",
        )

    def test_support_button_opens_a_tagged_chat(self):
        resp = self.client.get(reverse("room_list"))
        self.assertContains(resp, "https://wa.me/27717243852?text=" + quote("[Rooms4You app · Browse rooms]"))
        self.assertContains(resp, ">Help<")

    def test_room_page_support_note_names_the_room_and_says_it_is_not_the_landlord(self):
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertContains(resp, quote(f"Room #{self.room.id}: Spacious Single Room"))
        self.assertContains(resp, "this goes to our team, not the landlord")


class LoggedOutContactTests(TestCase):
    def setUp(self):
        cache.clear()
        self.room = make_room()

    def test_cards_say_contacts_unlock_with_a_free_account(self):
        resp = self.client.get(reverse("room_list"))
        self.assertContains(resp, "View room &amp; contact landlord")
        self.assertContains(resp, "unlock with a free account")
        self.assertContains(resp, "<strong>Sign up free</strong> to call or WhatsApp the landlord", html=True)

    def test_room_page_explains_and_offers_both_ways_in(self):
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        back = quote(f"/rooms/{self.room.id}/#contact-landlord", safe="/")
        self.assertContains(resp, "Sign in to contact Sipho")
        self.assertContains(resp, f'{reverse("register")}?next={back}')
        self.assertContains(resp, f'{reverse("login")}?next={back}')
        self.assertContains(resp, "Contact landlord · free sign-up")
        self.assertNotContains(resp, "+27821234567")

    def test_new_tenant_lands_back_on_the_contact_section(self):
        back = f"/rooms/{self.room.id}/#contact-landlord"
        self.client.post(reverse("register") + "?next=" + quote(back, safe="/"), {
            "role": "tenant", "persona": "student", "first_name": "Ayanda", "last_name": "Zulu",
            "email": "ayanda@example.com", "country_code": "+27", "phone_number": "0731234567",
            "terms_accepted": "on", "password1": PASSWORD, "password2": PASSWORD,
        })
        otp = PhoneOTP.objects.get(user__email="ayanda@example.com").otp

        resp = self.client.post(reverse("verify_account"), {"otp": otp})

        self.assertRedirects(resp, back, fetch_redirect_response=False)


class LoggedInContactTests(TestCase):
    def setUp(self):
        cache.clear()
        self.room = make_room()
        self.client.force_login(make_tenant())

    def test_cards_say_what_is_inside(self):
        resp = self.client.get(reverse("room_list"))
        self.assertContains(resp, "Tap for all photos, details and the landlord's number")
        self.assertNotContains(resp, "unlock with a free account")

    def test_room_page_explains_what_each_button_does(self):
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertContains(resp, "These go straight to Sipho")
        self.assertContains(resp, "Opens a WhatsApp chat with the landlord")
        self.assertNotContains(resp, "Sign in to contact")

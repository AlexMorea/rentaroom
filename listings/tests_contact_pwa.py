import re

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Room


def make_contact_room(owner, **kwargs):
    data = {
        "title": "Contact Test Room",
        "owner": owner,
        "description": "desc",
        "price": 1500,
        "location": "Loc",
        "suburb": "S",
        "town": "T",
        "city": "C",
        "full_address": "Addr",
        "postal_code": "0000",
        "room_type": Room.ROOM_TYPES[0][0],
        "contact_phone": "0821234567",
        "contact_email": "landlord@example.com",
    }
    data.update(kwargs)
    return Room.objects.create(**data)


class RoomDetailContactLinksTests(TestCase):
    """
    Regression coverage for: the "Call/WhatsApp/Email Landlord" buttons
    used target="_blank", which is unreliable inside an installed PWA
    (display: standalone in manifest.json) - there's no real "new tab"
    to open into. Same-window navigation to track_contact (which itself
    hands off to tel:/mailto:/wa.me via external_link.html) works
    identically in a normal browser tab and inside the standalone PWA.
    """

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="contact_owner", password="p")
        self.tenant = User.objects.create_user(username="contact_tenant", password="p")
        self.tenant.profile.role = "tenant"
        self.tenant.profile.save()
        self.room = make_contact_room(self.owner)
        self.client.force_login(self.tenant)

    def test_contact_buttons_have_no_target_blank(self):
        # The room detail page legitimately uses target="_blank"
        # elsewhere (social links, etc.) - this only checks the three
        # contact-action tags themselves, not the whole page.
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        content = resp.content.decode()

        for method in ("phone", "whatsapp", "email"):
            url = reverse("track_contact", args=[self.room.id, method])
            match = re.search(rf'<a[^>]*href="{re.escape(url)}"[^>]*>', content)
            assert match is not None, f"no <a> tag found for {url}"
            self.assertNotIn("target=", match.group(0))


class TrackContactEmailFallbackTests(TestCase):
    """
    mailto: only fires if the device has a default mail app registered -
    not guaranteed, especially on Android. The copy-to-clipboard
    fallback on external_link.html means that's never a dead end.
    """

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            username="fallback_owner", password="p", email="owner_fallback@example.com"
        )
        self.tenant = User.objects.create_user(username="fallback_tenant", password="p")
        self.tenant.profile.role = "tenant"
        self.tenant.profile.save()
        self.room = make_contact_room(self.owner, contact_email="landlord-direct@example.com")
        self.client.force_login(self.tenant)

    def test_email_contact_offers_copy_fallback(self):
        resp = self.client.get(reverse("track_contact", args=[self.room.id, "email"]))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["copy_value"], "landlord-direct@example.com")

        content = resp.content.decode()
        self.assertIn("landlord-direct@example.com", content)
        self.assertIn("copyValueBtn", content)

    def test_phone_and_whatsapp_contact_do_not_offer_copy_fallback(self):
        for method in ("phone", "whatsapp"):
            resp = self.client.get(reverse("track_contact", args=[self.room.id, method]))
            self.assertNotIn("copy_value", resp.context)

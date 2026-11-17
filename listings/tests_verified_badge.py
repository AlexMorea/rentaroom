from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile, Room


def make_room(owner, **kwargs):
    data = {
        "title": "R1",
        "owner": owner,
        "description": "desc",
        "price": 1000,
        "location": "Loc",
        "suburb": "S",
        "town": "T",
        "city": "C",
        "full_address": "Addr",
        "postal_code": "0000",
        "room_type": Room.ROOM_TYPES[0][0],
        "contact_phone": "0123456",
    }
    data.update(kwargs)
    return Room.objects.create(**data)


class RoomDetailVerifiedBadgeTests(TestCase):
    """
    room_detail previously hardcoded "Verified landlord" for every owner
    regardless of Profile.is_verified_landlord - a false trust claim on
    every single listing. Regression coverage for that fix.
    """

    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord", password="p", first_name="Sipho")
        self.tenant = User.objects.create_user(username="tenant", password="p")
        self.room = make_room(self.landlord)
        self.client.login(username="tenant", password="p")

    def test_unverified_landlord_is_not_labelled_verified(self):
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        body = resp.content.decode()

        self.assertIn("not yet verified", body)
        self.assertNotIn("★ Verified landlord", body)

    def test_verified_landlord_shows_verified_badge_and_email_check(self):
        profile = Profile.objects.get(user=self.landlord)
        profile.is_verified_landlord = True
        profile.is_phone_verified = True
        profile.is_email_verified = True
        profile.save()

        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        body = resp.content.decode()

        self.assertIn("★ Verified landlord", body)
        self.assertIn("Email verified", body)

    def test_phone_verified_is_never_shown_as_a_public_claim(self):
        """
        Regression coverage: is_phone_verified is set from the same
        email-delivered OTP as is_email_verified (see Profile model
        comment) - there's no real phone/SMS channel behind it. Showing
        it as a distinct "Phone verified" badge would be a false trust
        claim, and directly contradicts trust:verification.html, which
        lists real phone verification as "Coming Soon".
        """
        profile = Profile.objects.get(user=self.landlord)
        profile.is_phone_verified = True
        profile.is_email_verified = False
        profile.save()

        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        body = resp.content.decode()

        self.assertNotIn("Phone verified", body)


class CardBadgeLayoutTests(TestCase):
    """A status badge (Popular/Featured/New) must never hide the
    Verified badge - they live in different corners of the photo."""

    def test_popular_room_still_shows_verified(self):
        from django.contrib.auth.models import User
        from django.test import override_settings
        from django.urls import reverse

        from listings.models import Profile, Room

        owner = User.objects.create_user("verified-owner@example.com", password="x")
        Profile.objects.filter(user=owner).update(role="landlord", is_verified_landlord=True)
        room = Room.objects.create(
            owner=owner, title="Popular verified", description="d", location="Soweto",
            suburb="Orlando", town="Soweto", city="Johannesburg", full_address="1 St",
            postal_code="1804", room_type="Backroom", contact_phone="0821234567", price=1500,
        )
        Room.objects.filter(pk=room.pk).update(score=999)

        with override_settings(POPULAR_SCORE_THRESHOLD=1):
            body = self.client.get(reverse("room_list")).content.decode()

        self.assertIn("rc-badge-popular", body)
        self.assertIn('class="rc-verified-pill"', body)

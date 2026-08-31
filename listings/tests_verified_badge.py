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

    def test_verified_landlord_shows_verified_badge_and_checks(self):
        profile = Profile.objects.get(user=self.landlord)
        profile.is_verified_landlord = True
        profile.is_phone_verified = True
        profile.is_email_verified = True
        profile.save()

        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        body = resp.content.decode()

        self.assertIn("★ Verified landlord", body)
        self.assertIn("Phone verified", body)
        self.assertIn("Email verified", body)

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from listings.models import Contact, Review, Room


def make_room(owner, **kwargs):
    data = {
        "title": "Review Test Room",
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
        "is_available": True,
    }
    data.update(kwargs)
    return Room.objects.create(**data)


class AddReviewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username="owner", password="p")
        self.owner.profile.role = "landlord"
        self.owner.profile.save()
        self.room = make_room(self.owner)

        self.tenant = User.objects.create_user(username="tenant", password="p")
        self.tenant.profile.role = "tenant"
        self.tenant.profile.save()

    def test_review_without_contact_is_rejected(self):
        self.client.force_login(self.tenant)
        resp = self.client.post(
            reverse("add_review", args=[self.room.id]),
            {"rating": "5", "comment": "Great!"},
        )
        self.assertRedirects(resp, reverse("room_detail", args=[self.room.id]))
        self.assertFalse(Review.objects.filter(room=self.room, user=self.tenant).exists())

    def test_review_after_contact_is_accepted(self):
        Contact.objects.create(room=self.room, user=self.tenant)
        self.client.force_login(self.tenant)
        resp = self.client.post(
            reverse("add_review", args=[self.room.id]),
            {"rating": "4", "comment": "Nice place"},
        )
        self.assertRedirects(resp, reverse("room_detail", args=[self.room.id]))
        review = Review.objects.get(room=self.room, user=self.tenant)
        self.assertEqual(review.rating, 4)

    def test_out_of_range_rating_is_rejected(self):
        Contact.objects.create(room=self.room, user=self.tenant)
        self.client.force_login(self.tenant)
        resp = self.client.post(
            reverse("add_review", args=[self.room.id]),
            {"rating": "999", "comment": "x"},
        )
        self.assertRedirects(resp, reverse("room_detail", args=[self.room.id]))
        self.assertFalse(Review.objects.filter(room=self.room, user=self.tenant).exists())

    def test_non_numeric_rating_does_not_crash(self):
        Contact.objects.create(room=self.room, user=self.tenant)
        self.client.force_login(self.tenant)
        resp = self.client.post(
            reverse("add_review", args=[self.room.id]),
            {"rating": "not-a-number", "comment": "x"},
        )
        self.assertRedirects(resp, reverse("room_detail", args=[self.room.id]))
        self.assertFalse(Review.objects.filter(room=self.room, user=self.tenant).exists())

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from listings.models import Profile, Room, RoomImage


class CreateRoomTests(TestCase):
    """Publishing a room is the most important landlord action: it must
    work without a separate WhatsApp number, and a bad attachment must
    never lose the listing."""

    def setUp(self):
        self.landlord = User.objects.create_user("lister@example.com", "lister@example.com", "x", first_name="Nomsa")
        Profile.objects.filter(user=self.landlord).update(role="landlord", phone_number="0821234567")
        self.client.force_login(self.landlord)

    def data(self, **extra):
        data = {
            "title": "Neat room near the station", "description": "Clean room with its own entrance.",
            "price": "1600", "suburb": "Mabopane", "town": "Mabopane", "city": "Pretoria",
            "province": "Gauteng", "location": "Mabopane, Pretoria", "full_address": "12 Example Street",
            "postal_code": "0190", "room_type": "Single Room", "contact_phone": "0821234567",
            "contact_whatsapp": "", "total_units": "1", "available_units": "1",
            "availability_status": "now", "is_available": "on",
        }
        data.update(extra)
        return data

    def test_phone_is_prefilled_and_whatsapp_optional(self):
        page = self.client.get(reverse("create_room")).content.decode()
        self.assertIn("0821234567", page)
        self.assertIn("WhatsApp number (if different)", page)

    def test_publish_without_whatsapp_and_with_a_bad_file(self):
        bad = SimpleUploadedFile("lease.pdf", b"%PDF-1.4 not an image", content_type="application/pdf")
        resp = self.client.post(reverse("create_room"), {**self.data(), "images": [bad]})
        room = Room.objects.get(owner=self.landlord)
        self.assertRedirects(resp, reverse("upload_room_images", args=[room.id]), fetch_redirect_response=False)
        self.assertEqual(RoomImage.objects.filter(room=room).count(), 0)
        follow = self.client.get(reverse("upload_room_images", args=[room.id]))
        self.assertContains(follow, "couldn&#x27;t be added")

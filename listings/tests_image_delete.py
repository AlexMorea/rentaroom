from django.test import TestCase
from listings.models import Room, RoomImage
from django.contrib.auth.models import User
from unittest.mock import patch


class RoomImageDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.room = Room.objects.create(
            title="R1",
            owner=self.user,
            description="d",
            price=100,
            location="loc",
            suburb="sub",
            town="town",
            city="city",
            full_address="addr",
            postal_code="0000",
            room_type="Single Room",
            contact_phone="+271234",
        )

    @patch("cloudinary.uploader.destroy")
    def test_roomimage_delete_calls_cloudinary_destroy_when_needed(self, mock_destroy):
        # create RoomImage with a simple name (public_id)
        img = RoomImage.objects.create(room=self.room, image="test_public_id")

        # delete instance (triggers post_delete signal)
        img.delete()

        # uploader.destroy should have been called with our public id
        mock_destroy.assert_called()

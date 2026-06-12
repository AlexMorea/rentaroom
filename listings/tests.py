from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from .models import Room


class LandlordRoomsViewTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="landlord",
			email="landlord@example.com",
			password="pass",
		)

		# ensure profile exists and mark as landlord
		self.user.profile.role = "landlord"
		self.user.profile.save()

		# create 15 rooms so we have 2 pages (page size 10)
		for i in range(15):
			Room.objects.create(
				title=f"Room {i}",
				owner=self.user,
				description="Test room",
				price=Decimal("100.00"),
				location="Testville",
				suburb="Sub",
				town="Town",
				city="City",
				full_address="123 Test St",
				postal_code="0000",
				room_type="Single Room",
				contact_phone="0123456789",
			)

	def test_pagination_first_page(self):
		self.client.force_login(self.user)
		resp = self.client.get(reverse("landlord_rooms"))
		self.assertEqual(resp.status_code, 200)
		self.assertIn("page_obj", resp.context)
		page_obj = resp.context["page_obj"]
		self.assertEqual(page_obj.number, 1)
		self.assertEqual(len(resp.context["rooms"]), 10)
		self.assertEqual(page_obj.paginator.num_pages, 2)

	def test_pagination_second_page(self):
		self.client.force_login(self.user)
		resp = self.client.get(reverse("landlord_rooms") + "?page=2")
		self.assertEqual(resp.status_code, 200)
		page_obj = resp.context["page_obj"]
		self.assertEqual(page_obj.number, 2)
		self.assertEqual(len(resp.context["rooms"]), 5)

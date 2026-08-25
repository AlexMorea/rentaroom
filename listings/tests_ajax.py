from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Favorite, Profile, Room


class AjaxCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="anon_test", email="anon@example.com", password="pass")
        # create a room available for listing
        self.room = Room.objects.create(
            title="AJAX Room",
            owner=self.user,
            description="AJAX test",
            price=100,
            location="Testville",
            suburb="Sub",
            town="Town",
            city="City",
            full_address="123 Test St",
            postal_code="0000",
            room_type="Single Room",
            contact_phone="0123456789",
            is_available=True,
        )

    def test_ajax_caches_payload_as_anon(self):
        path = reverse("room_list") + "?ajax=1"
        cache_key = f"room_list:anon:{path}"

        self.assertIsNone(cache.get(cache_key))

        resp1 = self.client.get(path, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertIn("html", data1)
        self.assertIn("AJAX Room", data1["html"])

        # cache should now contain the payload
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached, data1)

        # subsequent request should return the same payload
        resp2 = self.client.get(path, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data2 = resp2.json()
        self.assertEqual(data2, data1)


class PermissionEdgeTests(TestCase):
    def setUp(self):
        # landlord owner and their profile
        self.owner = User.objects.create_user(username="landlord", email="landlord@example.com", password="pass")
        self.owner.profile.role = "landlord"
        self.owner.profile.save()

        # tenant user (to compare behavior)
        self.tenant = User.objects.create_user(username="tenant", email="tenant@example.com", password="pass")
        self.tenant.profile.role = "tenant"
        self.tenant.profile.save()

        # create a room owned by owner
        self.room = Room.objects.create(
            title="Owner Room",
            owner=self.owner,
            description="Test",
            price=100,
            location="City",
            suburb="Sub",
            town="Town",
            city="City",
            full_address="Addr",
            postal_code="0000",
            room_type="Single Room",
            contact_phone="0123456789",
            is_available=True,
        )

        # create a Favorite for the landlord user (should be ignored by view)
        Favorite.objects.create(user=self.owner, room=self.room)

    def test_landlord_with_favorite_does_not_see_saved_flag(self):
        # landlord logs in and views the room detail; is_saved should be False
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("is_saved", resp.context)
        self.assertFalse(resp.context["is_saved"])

    def test_tenant_with_favorite_sees_saved_flag(self):
        # tenant favorites the room and should see is_saved=True
        Favorite.objects.create(user=self.tenant, room=self.room)
        self.client.force_login(self.tenant)
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("is_saved", resp.context)
        self.assertTrue(resp.context["is_saved"])

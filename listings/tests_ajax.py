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


class ToggleFavoriteAjaxTests(TestCase):
    """
    toggle_favorite's non-AJAX branch (room_detail's own form, plain
    redirect) is exercised by the tests above via room_detail's context.
    This covers the AJAX branch the room-card grid's save heart uses
    (see static/js/room-card.js) - JSON in, JSON out, no redirect.
    """

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="fav_owner", password="p")

        self.tenant = User.objects.create_user(username="fav_tenant", password="p")
        self.tenant.profile.role = "tenant"
        self.tenant.profile.save()

        self.landlord = User.objects.create_user(username="fav_landlord", password="p")
        self.landlord.profile.role = "landlord"
        self.landlord.profile.save()

        self.room = Room.objects.create(
            title="Fav Room", owner=self.owner, description="Test", price=100,
            location="City", suburb="Sub", town="Town", city="City",
            full_address="Addr", postal_code="0000", room_type="Single Room",
            contact_phone="0123456789", is_available=True,
        )

    def _post_ajax(self, user):
        self.client.force_login(user)
        return self.client.post(
            reverse("toggle_favorite", args=[self.room.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_tenant_can_favorite_and_unfavorite_via_ajax(self):
        resp = self._post_ajax(self.tenant)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"favorited": True})
        self.assertTrue(Favorite.objects.filter(user=self.tenant, room=self.room).exists())

        resp = self._post_ajax(self.tenant)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"favorited": False})
        self.assertFalse(Favorite.objects.filter(user=self.tenant, room=self.room).exists())

    def test_non_tenant_gets_json_error_not_a_redirect(self):
        resp = self._post_ajax(self.landlord)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("error", resp.json())
        self.assertFalse(Favorite.objects.filter(user=self.landlord, room=self.room).exists())

    def test_anonymous_ajax_request_is_redirected_to_login(self):
        resp = self.client.post(
            reverse("toggle_favorite", args=[self.room.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_room_list_context_reports_favorited_ids_for_current_user(self):
        Favorite.objects.create(user=self.tenant, room=self.room)
        self.client.force_login(self.tenant)

        resp = self.client.get(reverse("room_list"))

        self.assertEqual(resp.status_code, 200)
        self.assertIn("favorited_ids", resp.context)
        self.assertIn(self.room.id, resp.context["favorited_ids"])

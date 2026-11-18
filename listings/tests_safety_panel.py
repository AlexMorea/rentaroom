from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase


class SafetyPanelVisibilityTests(TestCase):
    def tearDown(self):
        cache.clear()  # the room list caches its results

    def test_hidden_for_logged_out_visitors(self):
        resp = self.client.get("/rooms/")
        self.assertNotContains(resp, 'id="safetyToggle"')

    def test_shown_for_signed_in_users(self):
        user = User.objects.create_user(username="sp", email="sp@example.com", password="p", first_name="Thandi")
        self.client.force_login(user)
        resp = self.client.get("/rooms/")
        self.assertContains(resp, 'id="safetyToggle"')
        self.assertContains(resp, "Hi Thandi")

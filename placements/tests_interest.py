from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from listings.tests_freshness import make_room
from placements.models import Placement, PlacementStatusHistory


class InterestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.landlord = User.objects.create_user(username="ll", password="p", email="ll@example.com")
        self.tenant = User.objects.create_user(username="tt", password="p", email="tt@example.com")
        self.room = make_room(self.landlord, contact_whatsapp="0821234567")
        self.client.login(username="tt", password="p")

    def test_viewing_and_tapping_contact_buttons_is_not_interest(self):
        self.client.get(reverse("room_detail", args=[self.room.id]))
        for method in ("phone", "whatsapp", "email"):
            self.client.get(reverse("track_contact", args=[self.room.id, method]))
        self.assertFalse(Placement.objects.exists())

    def test_messaging_the_landlord_is_interest(self):
        self.client.post(reverse("conversation_thread", args=[self.room.id, self.landlord.id]),
                         {"body": "Hi, is the room still free?"})
        self.assertTrue(Placement.objects.filter(tenant=self.tenant, room=self.room).exists())

    def test_landlord_messaging_first_is_not_tenant_interest(self):
        self.client.login(username="ll", password="p")
        self.client.post(reverse("conversation_thread", args=[self.room.id, self.tenant.id]),
                         {"body": "Hi, the room is open again."})
        self.assertFalse(Placement.objects.exists())

    def test_im_interested_button_sends_message_and_then_shows_confirmation(self):
        page = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertContains(page, "I'm interested")
        self.client.post(reverse("conversation_thread", args=[self.room.id, self.landlord.id]),
                         {"body": "Hi, I'm interested in this room."})
        self.assertTrue(Placement.objects.filter(tenant=self.tenant, room=self.room).exists())
        page = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertContains(page, "told the landlord you're interested")


class GroupedStallReminderTests(TestCase):
    def test_four_stalled_enquiries_mean_one_email_each_side(self):
        landlord = User.objects.create_user(username="l2", password="p", email="l2@example.com")
        tenant = User.objects.create_user(username="t2", password="p", email="t2@example.com")
        for i in range(4):
            room = make_room(landlord, title=f"Room {i}")
            Placement.objects.create(tenant=tenant, landlord=landlord, room=room)
        Placement.objects.update(created_at=timezone.now() - timedelta(days=10))
        PlacementStatusHistory.objects.update(created_at=timezone.now() - timedelta(days=10))

        with patch("placements.management.commands.flag_stalled_placements.send_template_email") as mail, \
             patch("placements.management.commands.flag_stalled_placements.notify_user"):
            call_command("flag_stalled_placements")
            call_command("flag_stalled_placements")  # second run sends nothing more

        recipients = sorted(c.kwargs["to_email"] for c in mail.call_args_list)
        self.assertEqual(recipients, ["l2@example.com", "t2@example.com"])
        self.assertIn("these 4 rooms", [c for c in mail.call_args_list
                                         if c.kwargs["to_email"] == "t2@example.com"][0].kwargs["subject"])
        self.assertFalse(Placement.objects.filter(stall_nudge_sent_at__isnull=True).exists())

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Message, Profile, Room


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


def send(room, sender, recipient, minutes_ago):
    m = Message.objects.create(room=room, sender=sender, recipient=recipient, body="hi")
    Message.objects.filter(pk=m.pk).update(
        created_at=timezone.now() - timezone.timedelta(minutes=minutes_ago)
    )
    return m


class ProfileResponseTimeLabelTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord", password="p")

    def test_no_data_yields_no_label(self):
        profile = self.landlord.profile
        self.assertIsNone(profile.response_time_label)
        self.assertFalse(profile.is_fast_responder)

    def test_below_minimum_threads_yields_no_label(self):
        profile = self.landlord.profile
        profile.avg_response_minutes = 10
        profile.response_rate_percent = 100
        profile.responses_measured = Profile.MIN_THREADS_FOR_RESPONSE_LABEL - 1
        profile.save()
        self.assertIsNone(profile.response_time_label)

    def test_label_thresholds(self):
        profile = self.landlord.profile
        profile.responses_measured = 5

        cases = [
            (30, "Usually responds within an hour"),
            (120, "Usually responds within a few hours"),
            (600, "Usually responds within a day"),
            (2000, "Usually responds within a few days"),
            (10000, "Response time varies"),
        ]
        for minutes, expected in cases:
            profile.avg_response_minutes = minutes
            self.assertEqual(profile.response_time_label, expected)

    def test_is_fast_responder_requires_rate_and_speed(self):
        profile = self.landlord.profile
        profile.responses_measured = 5
        profile.avg_response_minutes = 100
        profile.response_rate_percent = 90
        self.assertTrue(profile.is_fast_responder)

        profile.response_rate_percent = 50
        self.assertFalse(profile.is_fast_responder)

        profile.response_rate_percent = 90
        profile.avg_response_minutes = 300
        self.assertFalse(profile.is_fast_responder)


class ComputeResponseStatsCommandTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord2", password="p")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        self.room = make_room(self.landlord)
        self.tenant1 = User.objects.create_user(username="tenant1", password="p")
        self.tenant2 = User.objects.create_user(username="tenant2", password="p")
        self.tenant3 = User.objects.create_user(username="tenant3", password="p")

    def test_dry_run_does_not_write(self):
        send(self.room, self.tenant1, self.landlord, 100)
        send(self.room, self.landlord, self.tenant1, 40)

        call_command("compute_response_stats")

        profile = Profile.objects.get(user=self.landlord)
        self.assertEqual(profile.responses_measured, 0)

    def test_force_computes_median_response_time_and_rate(self):
        # thread 1: 60 minute response
        send(self.room, self.tenant1, self.landlord, 100)
        send(self.room, self.landlord, self.tenant1, 40)
        # thread 2: 140 minute response
        send(self.room, self.tenant2, self.landlord, 200)
        send(self.room, self.landlord, self.tenant2, 60)
        # thread 3: no reply yet
        send(self.room, self.tenant3, self.landlord, 50)

        call_command("compute_response_stats", "--force")

        profile = Profile.objects.get(user=self.landlord)
        self.assertEqual(profile.avg_response_minutes, 100)  # median(60, 140)
        self.assertEqual(profile.response_rate_percent, 67)  # 2/3
        self.assertEqual(profile.responses_measured, 3)

    def test_landlord_initiated_message_is_not_counted_as_a_reply(self):
        # Landlord messages first, tenant never actually asked anything.
        send(self.room, self.landlord, self.tenant1, 100)

        call_command("compute_response_stats", "--force")

        profile = Profile.objects.get(user=self.landlord)
        self.assertEqual(profile.responses_measured, 0)
        self.assertIsNone(profile.avg_response_minutes)

    def test_only_first_reply_counts_not_later_replies_in_the_thread(self):
        send(self.room, self.tenant1, self.landlord, 100)  # tenant asks
        send(self.room, self.landlord, self.tenant1, 90)   # landlord replies (10 min)
        send(self.room, self.tenant1, self.landlord, 80)   # tenant follows up
        send(self.room, self.landlord, self.tenant1, 20)   # landlord replies again (much later)

        call_command("compute_response_stats", "--force")

        profile = Profile.objects.get(user=self.landlord)
        self.assertEqual(profile.avg_response_minutes, 10)
        self.assertEqual(profile.responses_measured, 1)

    def test_no_recent_threads_resets_stale_values(self):
        Profile.objects.filter(user=self.landlord).update(
            avg_response_minutes=30, response_rate_percent=100, responses_measured=5
        )

        call_command("compute_response_stats", "--force")

        profile = Profile.objects.get(user=self.landlord)
        self.assertIsNone(profile.avg_response_minutes)
        self.assertIsNone(profile.response_rate_percent)
        self.assertEqual(profile.responses_measured, 0)

    def test_landlord_with_no_messages_is_untouched(self):
        call_command("compute_response_stats", "--force")
        profile = Profile.objects.get(user=self.landlord)
        self.assertEqual(profile.responses_measured, 0)
        self.assertIsNone(profile.avg_response_minutes)


class ResponseTimeTemplateTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord3", password="p")
        Profile.objects.filter(user=self.landlord).update(
            role="landlord", avg_response_minutes=45, response_rate_percent=90, responses_measured=5
        )
        self.room = make_room(self.landlord)
        self.tenant = User.objects.create_user(username="tenant4", password="p")
        self.client.login(username="tenant4", password="p")

    def test_room_detail_shows_fast_responder_chip(self):
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        body = resp.content.decode()
        self.assertIn("Usually responds within an hour", body)
        self.assertIn("⚡", body)

    def test_room_card_shows_fast_responder_badge(self):
        resp = self.client.get(reverse("room_list"))
        self.assertContains(resp, "Fast responder")

    def test_landlord_profile_shows_response_time(self):
        resp = self.client.get(reverse("landlord_profile", args=[self.landlord.id]))
        body = resp.content.decode()
        self.assertIn("Fast Responder", body)
        self.assertIn("Usually responds within an hour", body)
        self.assertIn("90%", body)

    def test_no_signal_shown_for_landlord_without_enough_data(self):
        quiet_landlord = User.objects.create_user(username="quietlandlord", password="p")
        Profile.objects.filter(user=quiet_landlord).update(role="landlord")
        room = make_room(quiet_landlord, title="Quiet Room")

        resp = self.client.get(reverse("room_detail", args=[room.id]))
        body = resp.content.decode()
        self.assertNotIn("Usually responds", body)
        self.assertNotIn("Fast Responder", body)

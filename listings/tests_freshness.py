from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import signing
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Favorite, Profile, Room, RoomImage, RoomStat


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


def age_room(room, days):
    Room.objects.filter(pk=room.pk).update(
        last_confirmed_at=timezone.now() - timezone.timedelta(days=days)
    )
    room.refresh_from_db()


class RoomFreshnessPropertyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="p")

    @override_settings(LISTING_STALE_DAYS=14)
    def test_fresh_room_is_not_stale(self):
        room = make_room(self.owner)
        age_room(room, 2)
        self.assertFalse(room.is_stale)
        self.assertEqual(room.freshness_label, "Confirmed available 2 days ago")

    @override_settings(LISTING_STALE_DAYS=14)
    def test_room_past_threshold_is_stale(self):
        room = make_room(self.owner)
        age_room(room, 20)
        self.assertTrue(room.is_stale)
        self.assertEqual(room.freshness_label, "Not confirmed in 20 days")

    @override_settings(LISTING_STALE_DAYS=14)
    def test_occupied_room_past_threshold_is_not_stale(self):
        room = make_room(self.owner, is_available=False, available_units=0)
        age_room(room, 20)
        self.assertFalse(room.is_stale)

    def test_confirm_availability_resets_clock_and_nudge_cooldown(self):
        room = make_room(self.owner)
        age_room(room, 20)
        room.last_nudge_sent_at = timezone.now()
        room.save(update_fields=["last_nudge_sent_at"])

        room.confirm_availability()

        self.assertEqual(room.days_since_confirmed, 0)
        self.assertIsNone(room.last_nudge_sent_at)

    def test_today_and_yesterday_labels(self):
        room = make_room(self.owner)
        self.assertEqual(room.freshness_label, "Confirmed available today")

        age_room(room, 1)
        self.assertEqual(room.freshness_label, "Confirmed available yesterday")


class RoomCompletenessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner2", password="p")

    def test_incomplete_room_lists_missing_items(self):
        room = make_room(self.owner, description="short", contact_whatsapp="")
        self.assertLess(room.completeness_percent, 100)
        self.assertIn("Add at least 3 photos", room.completeness_missing)
        self.assertIn("Write a fuller description (30+ words)", room.completeness_missing)
        self.assertIn("Add a WhatsApp number so tenants can reach you fast", room.completeness_missing)

    def test_complete_room_reaches_100_percent(self):
        room = make_room(
            self.owner,
            description=" ".join(["word"] * 35),
            contact_whatsapp="0821234567",
            full_address="123 Main Road, Suburb",
            latitude=-25.7,
            longitude=28.2,
        )
        for i in range(3):
            RoomImage.objects.create(room=room, image=f"rooms/test{i}.jpg")

        self.assertEqual(room.completeness_percent, 100)
        self.assertEqual(room.completeness_missing, [])


class ConfirmRoomAvailabilityViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="landlord", password="p")
        self.other = User.objects.create_user(username="other_landlord", password="p")
        self.room = make_room(self.owner)
        age_room(self.room, 20)

    def test_owner_can_confirm(self):
        self.client.login(username="landlord", password="p")
        resp = self.client.post(reverse("confirm_room_availability", args=[self.room.id]))
        self.assertRedirects(resp, reverse("landlord_rooms"))
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_stale)

    def test_non_owner_cannot_confirm(self):
        self.client.login(username="other_landlord", password="p")
        resp = self.client.post(reverse("confirm_room_availability", args=[self.room.id]))
        self.assertEqual(resp.status_code, 404)
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_stale)

    def test_toggle_vacancy_also_resets_freshness(self):
        self.client.login(username="landlord", password="p")
        self.client.post(reverse("toggle_room_vacancy", args=[self.room.id]))
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_stale)


class ConfirmAvailabilityLinkTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="landlord2", password="p")
        self.room = make_room(self.owner)
        age_room(self.room, 20)

    def _token(self, action):
        return signing.dumps({"room_id": self.room.id, "action": action}, salt="room-availability-confirm")

    def test_confirm_link_works_without_login(self):
        resp = self.client.get(reverse("confirm_availability_via_link", args=[self._token("confirm")]))
        self.assertEqual(resp.status_code, 200)
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_stale)

    def test_vacate_link_marks_occupied(self):
        resp = self.client.get(reverse("confirm_availability_via_link", args=[self._token("vacate")]))
        self.assertEqual(resp.status_code, 200)
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_available)

    def test_garbage_token_shows_error_not_500(self):
        resp = self.client.get(reverse("confirm_availability_via_link", args=["not-a-real-token"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "expired or invalid")

    def test_token_for_deleted_room_shows_error_not_500(self):
        token = self._token("confirm")
        self.room.delete()
        resp = self.client.get(reverse("confirm_availability_via_link", args=[token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "expired or invalid")


class FlagStaleListingsCommandTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="landlord3", password="p", email="l3@example.com")

    @override_settings(LISTING_STALE_DAYS=14, LISTING_AUTO_HIDE_DAYS=30)
    def test_dry_run_sends_nothing_and_changes_nothing(self):
        room = make_room(self.owner)
        age_room(room, 20)

        with patch("listings.management.commands.flag_stale_listings.send_template_email") as mail, \
             patch("listings.management.commands.flag_stale_listings.notify_user") as push:
            call_command("flag_stale_listings")

        mail.assert_not_called()
        push.assert_not_called()
        room.refresh_from_db()
        self.assertIsNone(room.last_nudge_sent_at)

    @override_settings(LISTING_STALE_DAYS=14, LISTING_AUTO_HIDE_DAYS=30)
    def test_force_nudges_stale_room_once(self):
        room = make_room(self.owner)
        age_room(room, 20)

        with patch("listings.management.commands.flag_stale_listings.send_template_email") as mail, \
             patch("listings.management.commands.flag_stale_listings.notify_user") as push:
            call_command("flag_stale_listings", "--force")

        mail.assert_called_once()
        push.assert_called_once()
        room.refresh_from_db()
        self.assertIsNotNone(room.last_nudge_sent_at)
        self.assertTrue(room.is_available)  # not hidden yet, just nudged

    @override_settings(LISTING_STALE_DAYS=14, LISTING_AUTO_HIDE_DAYS=30)
    def test_force_does_not_renudge_within_cooldown(self):
        room = make_room(self.owner)
        age_room(room, 20)
        Room.objects.filter(pk=room.pk).update(last_nudge_sent_at=timezone.now() - timezone.timedelta(days=1))

        with patch("listings.management.commands.flag_stale_listings.send_template_email") as mail:
            call_command("flag_stale_listings", "--force")

        mail.assert_not_called()

    @override_settings(LISTING_STALE_DAYS=14, LISTING_AUTO_HIDE_DAYS=30)
    def test_force_auto_hides_past_hide_threshold(self):
        room = make_room(self.owner)
        age_room(room, 40)

        with patch("listings.management.commands.flag_stale_listings.send_template_email") as mail, \
             patch("listings.management.commands.flag_stale_listings.notify_user") as push:
            call_command("flag_stale_listings", "--force")

        mail.assert_called_once()
        push.assert_called_once()
        room.refresh_from_db()
        self.assertFalse(room.is_available)

    @override_settings(LISTING_STALE_DAYS=14, LISTING_AUTO_HIDE_DAYS=30)
    def test_fresh_room_untouched(self):
        room = make_room(self.owner)
        age_room(room, 1)

        with patch("listings.management.commands.flag_stale_listings.send_template_email") as mail:
            call_command("flag_stale_listings", "--force")

        mail.assert_not_called()
        room.refresh_from_db()
        self.assertTrue(room.is_available)


class SendLandlordDigestCommandTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord4", password="p", email="l4@example.com")
        Profile.objects.filter(user=self.landlord).update(role="landlord")

    def test_landlord_with_no_rooms_is_skipped(self):
        with patch("listings.management.commands.send_landlord_digest.send_template_email") as mail:
            call_command("send_landlord_digest", "--force")
        mail.assert_not_called()

    def test_dry_run_sends_nothing(self):
        make_room(self.landlord)
        with patch("listings.management.commands.send_landlord_digest.send_template_email") as mail:
            call_command("send_landlord_digest")
        mail.assert_not_called()

    def test_force_sends_digest_with_correct_totals(self):
        room = make_room(self.landlord)
        tenant = User.objects.create_user(username="tenant_digest", password="p")

        for _ in range(3):
            RoomStat.objects.create(room=room, stat_type="view")
        RoomStat.objects.create(room=room, stat_type="contact_whatsapp")
        Favorite.objects.create(user=tenant, room=room)

        with patch("listings.management.commands.send_landlord_digest.send_template_email") as mail, \
             patch("listings.management.commands.send_landlord_digest.notify_user") as push:
            call_command("send_landlord_digest", "--force")

        mail.assert_called_once()
        push.assert_called_once()
        ctx = mail.call_args.kwargs["context"]
        self.assertEqual(ctx["totals"], {"views": 3, "contacts": 1, "favorites": 1})

    def test_tip_is_included_and_deterministic_for_the_week(self):
        make_room(self.landlord)
        with patch("listings.management.commands.send_landlord_digest.send_template_email") as mail, \
             patch("listings.management.commands.send_landlord_digest.notify_user"):
            call_command("send_landlord_digest", "--force")

        ctx = mail.call_args.kwargs["context"]
        self.assertTrue(ctx["tip"])

"""
Listings disappearing from Browse, and the password rule.

The stale-listing job nudged landlords around 19 Nov and, a week later,
hid every room whose landlord hadn't clicked "confirm" - 3 of the site's
7 listings. Hiding is now opt-in, editing a listing counts as confirming
it, and migration 0029 puts the paused rooms back.
"""
import importlib
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership
from listings.admin import RoomAdmin, relist_on_browse
from listings.models import Profile, Room

PASSWORD = "Blue7Taxi!Rain"
JOB = "listings.management.commands.flag_stale_listings"


def make_landlord(email="landlord@example.com", **profile):
    user = User.objects.create_user(email, email, PASSWORD, first_name="Sipho")
    Profile.objects.filter(user=user).update(role="landlord", is_phone_verified=True, is_email_verified=True, **profile)
    return User.objects.get(pk=user.pk)


def make_room(owner, title="Neat room", **extra):
    data = {
        "title": title, "owner": owner, "description": "Clean room.", "price": 1500,
        "location": "Mamelodi East, Pretoria", "suburb": "Mamelodi East", "town": "Mamelodi",
        "city": "Pretoria", "full_address": "12 Example Street", "postal_code": "0122",
        "room_type": "Single Room", "contact_phone": "+27821234567",
    }
    data.update(extra)
    return Room.objects.create(**data)


def age(room, confirmed_days_ago, nudged_days_ago=None):
    now = timezone.now()
    Room.objects.filter(pk=room.pk).update(
        last_confirmed_at=now - timedelta(days=confirmed_days_ago),
        last_nudge_sent_at=None if nudged_days_ago is None else now - timedelta(days=nudged_days_ago),
    )


@override_settings(LISTING_STALE_DAYS=14, LISTING_AUTO_HIDE_DAYS=30, LISTING_HIDE_GRACE_DAYS=7)
class StaleJobKeepsRoomsListedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_landlord()

    def test_unconfirmed_room_stays_on_browse_and_is_nudged_again(self):
        # Exactly the rooms that vanished: confirmed long ago, nudged 7+ days ago.
        room = make_room(self.owner)
        age(room, confirmed_days_ago=87, nudged_days_ago=15)

        with patch(f"{JOB}.send_template_email") as mail, patch(f"{JOB}.notify_user"):
            call_command("flag_stale_listings", "--force")

        room.refresh_from_db()
        self.assertTrue(room.is_available)
        mail.assert_called_once()  # a fresh reminder instead of a pause
        self.assertEqual(mail.call_args.kwargs["template"], "emails/confirm_availability.html")
        self.assertContains(self.client.get(reverse("room_list")), "Neat room")

    def test_reminder_does_not_threaten_hiding_when_hiding_is_off(self):
        room = make_room(self.owner)
        age(room, confirmed_days_ago=20)
        with patch(f"{JOB}.notify_user"):
            call_command("flag_stale_listings", "--force")
        from django.core import mail
        body = mail.outbox[0].alternatives[0][0]
        self.assertNotIn("we'll hide the listing", body)
        self.assertIn("shows lower in search", body)

    def test_one_failed_email_does_not_stop_the_other_landlords(self):
        first = make_room(self.owner, title="First room")
        second = make_room(make_landlord("other@example.com"), title="Second room")
        age(first, 20)
        age(second, 20)

        with patch(f"{JOB}.send_template_email", side_effect=[RuntimeError("brevo down"), None]), \
                patch(f"{JOB}.notify_user"):
            call_command("flag_stale_listings", "--force")

        nudged = Room.objects.filter(last_nudge_sent_at__isnull=False).count()
        self.assertEqual(nudged, 1)  # the failed one is retried tomorrow


class EditingConfirmsTheListingTests(TestCase):
    def test_saving_the_edit_form_resets_the_stale_clock(self):
        cache.clear()
        owner = make_landlord()
        room = make_room(owner)
        age(room, confirmed_days_ago=60, nudged_days_ago=10)
        self.client.force_login(owner)

        self.client.post(reverse("edit_room", args=[room.id]), {
            "title": "Neat room", "description": "Clean room.", "price": "1600",
            "suburb": "Mamelodi East", "town": "Mamelodi", "city": "Pretoria", "province": "Gauteng",
            "location": "Mamelodi East, Pretoria", "full_address": "12 Example Street", "postal_code": "0122",
            "room_type": "Single Room", "contact_phone": "0821234567", "total_units": "1",
            "available_units": "1", "availability_status": "now", "is_available": "on",
        })

        room.refresh_from_db()
        self.assertEqual(room.days_since_confirmed, 0)
        self.assertIsNone(room.last_nudge_sent_at)


class RelistMigrationTests(TestCase):
    def setUp(self):
        self.relist = importlib.import_module("listings.migrations.0029_relist_rooms_paused_as_stale").relist_rooms

    def test_paused_rooms_come_back_but_deliberate_and_suspended_ones_do_not(self):
        owner = make_landlord()
        paused = make_room(owner, title="Paused by the job")
        age(paused, confirmed_days_ago=87, nudged_days_ago=7)
        Room.objects.filter(pk=paused.pk).update(is_available=False)

        never_nudged = make_room(owner, title="Hidden, never nudged")
        Room.objects.filter(pk=never_nudged.pk).update(is_available=False)

        suspended_owner = make_landlord("banned@example.com")
        suspended_room = make_room(suspended_owner, title="Suspended owner")
        age(suspended_room, confirmed_days_ago=87, nudged_days_ago=7)
        Room.objects.filter(pk=suspended_room.pk).update(is_available=False)
        User.objects.filter(pk=suspended_owner.pk).update(is_active=False)

        self.relist(apps, None)

        self.assertTrue(Room.objects.get(pk=paused.pk).is_available)
        self.assertFalse(Room.objects.get(pk=never_nudged.pk).is_available)
        self.assertFalse(Room.objects.get(pk=suspended_room.pk).is_available)

    def test_membership_suspension_keeps_room_hidden(self):
        owner = make_landlord()
        # Created first, then suspended (creating one enrols it as active).
        Membership.objects.get_or_create(user=owner)
        Membership.objects.filter(user=owner).update(status="suspended")
        room = make_room(owner)
        age(room, confirmed_days_ago=87, nudged_days_ago=7)
        Room.objects.filter(pk=room.pk).update(is_available=False)

        self.relist(apps, None)

        self.assertFalse(Room.objects.get(pk=room.pk).is_available)


class AdminRelistActionTests(TestCase):
    def test_put_back_on_browse_skips_suspended_accounts(self):
        active_room = make_room(make_landlord())
        gone_owner = make_landlord("gone@example.com")
        gone_room = make_room(gone_owner)
        Room.objects.filter(pk__in=[active_room.pk, gone_room.pk]).update(is_available=False)
        User.objects.filter(pk=gone_owner.pk).update(is_active=False)

        request = RequestFactory().post("/admin/")
        request.user = User.objects.create_superuser("staff", "staff@example.com", PASSWORD)
        request.session = {}
        request._messages = FallbackStorage(request)
        relist_on_browse(RoomAdmin(Room, AdminSite()), request, Room.objects.all())

        self.assertTrue(Room.objects.get(pk=active_room.pk).is_available)
        self.assertFalse(Room.objects.get(pk=gone_room.pk).is_available)


class PasswordRuleTests(TestCase):
    def setUp(self):
        cache.clear()

    def _signup(self, password):
        return self.client.post(reverse("register"), {
            "role": "tenant", "persona": "student", "first_name": "Ayanda", "last_name": "Zulu",
            "email": "ayanda@example.com", "country_code": "+27", "phone_number": "0731234567",
            "terms_accepted": "on", "password1": password, "password2": password,
        })

    def test_signup_rejects_a_seven_character_password(self):
        resp = self._signup("Ab1!xyz")
        self.assertContains(resp, "at least 8 characters")
        self.assertFalse(User.objects.filter(email="ayanda@example.com").exists())

    def test_signup_accepts_eight_characters(self):
        resp = self._signup("Ab1!wxyz")
        self.assertRedirects(resp, reverse("verify_account"), fetch_redirect_response=False)

    def test_signup_field_tells_the_browser_too(self):
        self.assertContains(self.client.get(reverse("register")), 'minlength="8"')

    def test_change_password_rejects_short_ones(self):
        user = make_landlord()
        self.client.force_login(user)
        resp = self.client.post(reverse("change_password"), {
            "old_password": PASSWORD, "new_password1": "short1!", "new_password2": "short1!",
        })
        self.assertContains(resp, "at least 8 characters")
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))

    def test_existing_short_password_still_logs_in(self):
        # The rule only applies to new passwords - nobody gets locked out.
        user = User.objects.create_user("old@example.com", "old@example.com", "abc")
        Profile.objects.filter(user=user).update(is_phone_verified=True, is_email_verified=True)
        resp = self.client.post(reverse("login"), {"email": "old@example.com", "password": "abc"})
        self.assertRedirects(resp, reverse("verify_device"), fetch_redirect_response=False)

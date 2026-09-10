from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from listings.models import Contact, Profile, Room
from placements.models import Waitlist


def make_room(owner, **kwargs):
    data = {
        "title": "Waitlist Room",
        "owner": owner,
        "description": "desc",
        "price": 1500,
        "location": "Loc",
        "suburb": "S",
        "town": "T",
        "city": "C",
        "full_address": "Addr",
        "postal_code": "0000",
        "room_type": Room.ROOM_TYPES[0][0],
        "contact_phone": "0821234567",
    }
    data.update(kwargs)
    return Room.objects.create(**data)


def make_full_room(owner, **kwargs):
    """A room that's occupied now but expected available from a future
    date - still listed (is_available=True) so it can carry a waitlist."""
    data = {
        "availability_status": "from",
        "available_units": 0,
        "available_from": timezone.localdate() + timezone.timedelta(days=14),
        "is_available": True,
    }
    data.update(kwargs)
    return make_room(owner, **data)


class WaitlistModelTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord", password="p")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        self.room = make_full_room(self.landlord)

        self.tenant1 = User.objects.create_user(username="tenant1", password="p", email="t1@example.com")
        self.tenant2 = User.objects.create_user(username="tenant2", password="p", email="t2@example.com")

    def test_position_is_fifo(self):
        entry1 = Waitlist.objects.create(tenant=self.tenant1, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_TENANT)
        entry2 = Waitlist.objects.create(tenant=self.tenant2, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_TENANT)

        self.assertEqual(entry1.position, 1)
        self.assertEqual(entry2.position, 2)

    def test_uniqueness_per_tenant_and_room(self):
        Waitlist.objects.create(tenant=self.tenant1, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_TENANT)

        with self.assertRaises(Exception):
            Waitlist.objects.create(tenant=self.tenant1, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_TENANT)

    def test_notify_all_for_room_marks_notified_and_emails(self):
        entry1 = Waitlist.objects.create(tenant=self.tenant1, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_TENANT)
        entry2 = Waitlist.objects.create(tenant=self.tenant2, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_TENANT)

        notified = Waitlist.notify_all_for_room(self.room)

        self.assertEqual(notified, 2)
        entry1.refresh_from_db()
        entry2.refresh_from_db()
        self.assertEqual(entry1.status, Waitlist.STATUS_NOTIFIED)
        self.assertEqual(entry2.status, Waitlist.STATUS_NOTIFIED)
        self.assertIsNotNone(entry1.notified_at)
        self.assertEqual(len(mail.outbox), 2)

    def test_notify_all_for_room_skips_cancelled_entries(self):
        Waitlist.objects.create(
            tenant=self.tenant1, room=self.room, landlord=self.landlord,
            added_by=Waitlist.ADDED_BY_TENANT, status=Waitlist.STATUS_CANCELLED,
        )

        notified = Waitlist.notify_all_for_room(self.room)

        self.assertEqual(notified, 0)
        self.assertEqual(len(mail.outbox), 0)


class RoomAvailabilitySignalTests(TestCase):
    """
    Covers the actual business trigger: a landlord marking a full,
    waitlisted room available again should fire notifications - without
    the landlord (or any view) having to know the waitlist exists.
    """

    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord2", password="p")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        self.room = make_full_room(self.landlord)
        self.tenant = User.objects.create_user(username="tenant3", password="p", email="t3@example.com")
        self.entry = Waitlist.objects.create(
            tenant=self.tenant, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_TENANT
        )

    def test_room_becoming_available_notifies_waitlist(self):
        self.room.availability_status = "now"
        self.room.available_units = 1
        self.room.save()

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, Waitlist.STATUS_NOTIFIED)
        self.assertEqual(len(mail.outbox), 1)

    def test_unrelated_save_does_not_notify(self):
        self.room.description = "Updated description, nothing about availability"
        self.room.save()

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, Waitlist.STATUS_WAITING)
        self.assertEqual(len(mail.outbox), 0)

    def test_marking_fully_unavailable_does_not_notify(self):
        self.room.is_available = False
        self.room.save()

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, Waitlist.STATUS_WAITING)
        self.assertEqual(len(mail.outbox), 0)


class JoinLeaveWaitlistViewTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord3", password="p")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        self.room = make_full_room(self.landlord)

        self.tenant = User.objects.create_user(username="tenant4", password="p")
        Profile.objects.filter(user=self.tenant).update(role="tenant")

        self.client.force_login(self.tenant)

    def test_tenant_can_join_waitlist_for_full_room(self):
        resp = self.client.post(reverse("placements:join_waitlist", args=[self.room.id]))

        self.assertRedirects(resp, reverse("room_detail", args=[self.room.id]))
        entry = Waitlist.objects.get(tenant=self.tenant, room=self.room)
        self.assertEqual(entry.status, Waitlist.STATUS_WAITING)
        self.assertEqual(entry.added_by, Waitlist.ADDED_BY_TENANT)

    def test_joining_twice_does_not_duplicate(self):
        self.client.post(reverse("placements:join_waitlist", args=[self.room.id]))
        self.client.post(reverse("placements:join_waitlist", args=[self.room.id]))

        self.assertEqual(Waitlist.objects.filter(tenant=self.tenant, room=self.room).count(), 1)

    def test_cannot_join_waitlist_for_room_with_vacancy(self):
        available_room = make_room(self.landlord, title="Open Room")

        self.client.post(reverse("placements:join_waitlist", args=[available_room.id]))

        self.assertFalse(Waitlist.objects.filter(tenant=self.tenant, room=available_room).exists())

    def test_tenant_can_leave_waitlist(self):
        self.client.post(reverse("placements:join_waitlist", args=[self.room.id]))
        resp = self.client.post(reverse("placements:leave_waitlist", args=[self.room.id]))

        self.assertRedirects(resp, reverse("room_detail", args=[self.room.id]))
        entry = Waitlist.objects.get(tenant=self.tenant, room=self.room)
        self.assertEqual(entry.status, Waitlist.STATUS_CANCELLED)

    def test_rejoining_after_leaving_reactivates_entry(self):
        self.client.post(reverse("placements:join_waitlist", args=[self.room.id]))
        self.client.post(reverse("placements:leave_waitlist", args=[self.room.id]))
        self.client.post(reverse("placements:join_waitlist", args=[self.room.id]))

        entry = Waitlist.objects.get(tenant=self.tenant, room=self.room)
        self.assertEqual(entry.status, Waitlist.STATUS_WAITING)
        self.assertEqual(Waitlist.objects.filter(tenant=self.tenant, room=self.room).count(), 1)

    def test_room_detail_shows_join_button_for_full_room(self):
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertContains(resp, "Join Waitlist")

    def test_room_detail_shows_leave_button_once_joined(self):
        self.client.post(reverse("placements:join_waitlist", args=[self.room.id]))
        resp = self.client.get(reverse("room_detail", args=[self.room.id]))
        self.assertContains(resp, "On waitlist (#1)")

    def test_room_detail_has_no_waitlist_card_for_available_room(self):
        available_room = make_room(self.landlord, title="Open Room 2")
        resp = self.client.get(reverse("room_detail", args=[available_room.id]))
        self.assertNotContains(resp, "Join Waitlist")


class LandlordWaitlistManagementTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord5", password="p")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        self.room = make_full_room(self.landlord)

        self.engaged_tenant = User.objects.create_user(username="tenant5", password="p")
        Profile.objects.filter(user=self.engaged_tenant).update(role="tenant")
        Contact.objects.create(room=self.room, user=self.engaged_tenant)

        self.stranger_tenant = User.objects.create_user(username="tenant6", password="p")
        Profile.objects.filter(user=self.stranger_tenant).update(role="tenant")

        self.client.force_login(self.landlord)

    def test_room_waitlist_page_lists_addable_engaged_tenants(self):
        resp = self.client.get(reverse("placements:room_waitlist", args=[self.room.id]))
        self.assertContains(resp, "tenant5")
        self.assertNotContains(resp, "tenant6")

    def test_landlord_can_add_engaged_tenant(self):
        resp = self.client.post(
            reverse("placements:add_to_waitlist", args=[self.room.id]),
            {"tenant_id": self.engaged_tenant.id},
        )
        self.assertRedirects(resp, reverse("placements:room_waitlist", args=[self.room.id]))
        entry = Waitlist.objects.get(tenant=self.engaged_tenant, room=self.room)
        self.assertEqual(entry.added_by, Waitlist.ADDED_BY_LANDLORD)

    def test_landlord_cannot_add_tenant_who_never_engaged(self):
        self.client.post(
            reverse("placements:add_to_waitlist", args=[self.room.id]),
            {"tenant_id": self.stranger_tenant.id},
        )
        self.assertFalse(Waitlist.objects.filter(tenant=self.stranger_tenant, room=self.room).exists())

    def test_landlord_can_remove_entry(self):
        entry = Waitlist.objects.create(
            tenant=self.engaged_tenant, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_LANDLORD
        )
        self.client.post(reverse("placements:remove_from_waitlist", args=[entry.id]))
        entry.refresh_from_db()
        self.assertEqual(entry.status, Waitlist.STATUS_CANCELLED)

    def test_other_landlord_cannot_manage_this_room_waitlist(self):
        other_landlord = User.objects.create_user(username="landlord6", password="p")
        Profile.objects.filter(user=other_landlord).update(role="landlord")
        entry = Waitlist.objects.create(
            tenant=self.engaged_tenant, room=self.room, landlord=self.landlord, added_by=Waitlist.ADDED_BY_LANDLORD
        )

        self.client.force_login(other_landlord)
        resp = self.client.post(reverse("placements:remove_from_waitlist", args=[entry.id]))

        self.assertEqual(resp.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.status, Waitlist.STATUS_WAITING)


class TenantProfileViewTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord7", password="p")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        self.room = make_room(self.landlord)

        self.engaged_tenant = User.objects.create_user(username="tenant7", password="p", first_name="Sam")
        Profile.objects.filter(user=self.engaged_tenant).update(role="tenant")
        Contact.objects.create(room=self.room, user=self.engaged_tenant)

        self.stranger_tenant = User.objects.create_user(username="tenant8", password="p")
        Profile.objects.filter(user=self.stranger_tenant).update(role="tenant")

        self.client.force_login(self.landlord)

    def test_landlord_can_view_engaged_tenant_profile(self):
        resp = self.client.get(reverse("tenant_profile", args=[self.engaged_tenant.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sam")

    def test_landlord_cannot_view_unengaged_tenant_profile(self):
        resp = self.client.get(reverse("tenant_profile", args=[self.stranger_tenant.id]))
        self.assertEqual(resp.status_code, 404)

    def test_other_landlord_cannot_view_via_unrelated_engagement(self):
        other_landlord = User.objects.create_user(username="landlord8", password="p")
        Profile.objects.filter(user=other_landlord).update(role="landlord")

        self.client.force_login(other_landlord)
        resp = self.client.get(reverse("tenant_profile", args=[self.engaged_tenant.id]))
        self.assertEqual(resp.status_code, 404)

    def test_tenant_cannot_view_tenant_profile_page(self):
        self.client.force_login(self.engaged_tenant)
        resp = self.client.get(reverse("tenant_profile", args=[self.stranger_tenant.id]))
        self.assertEqual(resp.status_code, 302)  # user_passes_test redirects non-landlords

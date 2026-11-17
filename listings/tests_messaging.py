from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from listings.models import BlockedUser, Message, Profile, Room
from trust.models import FraudReport

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class MessagingTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user("ll@example.com", "ll@example.com", "x", first_name="Thandi")
        self.tenant = User.objects.create_user("tn@example.com", "tn@example.com", "x", first_name="Lerato")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        Profile.objects.filter(user=self.tenant).update(role="tenant")
        self.room = Room.objects.create(
            owner=self.landlord, title="Sunny room", description="d", location="Soweto", suburb="Orlando",
            town="Soweto", city="Johannesburg", full_address="1 St", postal_code="1804",
            room_type="Backroom", contact_phone="0821234567", price=1500,
        )
        self.thread = reverse("conversation_thread", args=[self.room.id, self.landlord.id])

    def send(self, client, url, body, ajax=True):
        return client.post(url, {"body": body}, **(AJAX if ajax else {}))

    def test_send_returns_json_and_emails_first_unread_only(self):
        self.client.force_login(self.tenant)
        mail.outbox.clear()

        resp = self.send(self.client, self.thread, "Is it available?")
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["message"]["body"], "Is it available?")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ll@example.com"])
        self.assertIn("Lerato", mail.outbox[0].subject)

        self.send(self.client, self.thread, "Can I view Saturday?")
        self.assertEqual(len(mail.outbox), 1)  # still unread: no second email

        # Landlord reads it, so the tenant's next message emails again.
        landlord = self.client_class()
        landlord.force_login(self.landlord)
        landlord.get(reverse("conversation_thread", args=[self.room.id, self.tenant.id]))
        self.send(self.client, self.thread, "Hello again")
        self.assertEqual(len(mail.outbox), 2)

    def test_plain_form_post_still_works(self):
        self.client.force_login(self.tenant)
        resp = self.send(self.client, self.thread, "No JavaScript here", ajax=False)
        self.assertRedirects(resp, self.thread)
        self.assertTrue(Message.objects.filter(body="No JavaScript here").exists())

    def test_unread_badge_poll_and_seen(self):
        self.client.force_login(self.tenant)
        self.send(self.client, self.thread, "Hi")

        landlord = self.client_class()
        landlord.force_login(self.landlord)
        summary = landlord.get(reverse("unread_summary")).json()
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["latest"]["from"], "Lerato")

        page = landlord.get(reverse("inbox"))
        self.assertContains(page, 'data-unread-badge')
        self.assertContains(page, "ib-unread")

        # Landlord polls the open thread: message is now read.
        poll = landlord.get(reverse("conversation_poll", args=[self.room.id, self.tenant.id]) + "?after=0").json()
        self.assertEqual(len(poll["messages"]), 1)
        self.assertEqual(landlord.get(reverse("unread_summary")).json()["count"], 0)

        # Tenant's poll now reports the message as seen.
        mine = self.client.get(reverse("conversation_poll", args=[self.room.id, self.landlord.id]) + "?after=0").json()
        self.assertTrue(mine["last_mine_read"])

    def test_block_stops_messages_both_ways(self):
        self.client.force_login(self.landlord)
        landlord_thread = reverse("conversation_thread", args=[self.room.id, self.tenant.id])
        self.client.post(reverse("toggle_block", args=[self.room.id, self.tenant.id]))
        self.assertTrue(BlockedUser.objects.filter(blocker=self.landlord, blocked=self.tenant).exists())

        tenant = self.client_class()
        tenant.force_login(self.tenant)
        resp = self.send(tenant, self.thread, "Hello?")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Message.objects.exists())
        self.assertContains(self.client.get(landlord_thread), "You've blocked")

        self.client.post(reverse("toggle_block", args=[self.room.id, self.tenant.id]))
        self.assertTrue(self.send(tenant, self.thread, "Hello?").json()["ok"])

    def test_report_attaches_transcript(self):
        self.client.force_login(self.tenant)
        self.send(self.client, self.thread, "Please pay the deposit first")
        self.client.post(reverse("report_conversation", args=[self.room.id, self.landlord.id]), {"kind": "scam"})
        report = FraudReport.objects.filter(reported_user=self.landlord).latest("id")
        self.assertIn("Please pay the deposit first", report.detail)
        self.assertEqual(report.room, self.room)

    def test_strangers_cannot_open_or_poll(self):
        stranger = User.objects.create_user("s@example.com", "s@example.com", "x")
        self.client.force_login(stranger)
        other_thread = reverse("conversation_thread", args=[self.room.id, self.tenant.id])
        self.assertEqual(self.client.get(other_thread).status_code, 403)
        poll = reverse("conversation_poll", args=[self.room.id, self.tenant.id])
        self.assertEqual(self.client.get(poll).status_code, 403)


class LandlordDashboardTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user("dash@example.com", "dash@example.com", "x", first_name="Thandi")
        Profile.objects.filter(user=self.landlord).update(role="landlord")
        self.client.force_login(self.landlord)

    def test_new_landlord_sees_first_listing_choices(self):
        body = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("What would you like to list?", body)
        self.assertNotIn("Needs your attention", body)

    def test_attention_list_points_at_real_work(self):
        room = Room.objects.create(
            owner=self.landlord, title="Room with no photos", description="d", location="Soweto",
            suburb="Orlando", town="Soweto", city="Johannesburg", full_address="1 St", postal_code="1804",
            room_type="Backroom", contact_phone="0821234567", price=1500,
        )
        tenant = User.objects.create_user("t2@example.com", "t2@example.com", "x", first_name="Lerato")
        Message.objects.create(room=room, sender=tenant, recipient=self.landlord, body="Hi")
        body = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Needs your attention", body)
        self.assertIn("1 unread message", body)
        self.assertIn("has no photos", body)
        self.assertIn(reverse("upload_room_images", args=[room.id]), body)
        # Listings come before the membership/placements cards.
        self.assertLess(body.index("Your listings"), body.index("ld-placements-card"))

    def test_add_room_page_is_stepped(self):
        body = self.client.get(reverse("create_room")).content.decode()
        self.assertEqual(body.count('class="cr-step form-grid"'), 4)
        self.assertIn("room-steps", body)


class DeleteRoomTests(TestCase):
    def test_delete_button_posts_and_link_cannot_delete(self):
        landlord = User.objects.create_user("del@example.com", "del@example.com", "x")
        Profile.objects.filter(user=landlord).update(role="landlord")
        room = Room.objects.create(
            owner=landlord, title="To delete", description="d", location="Soweto", suburb="Orlando",
            town="Soweto", city="Johannesburg", full_address="1 St", postal_code="1804",
            room_type="Backroom", contact_phone="0821234567", price=1500,
        )
        self.client.force_login(landlord)
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn(f'<form method="post" action="{reverse("delete_room", args=[room.id])}"', page)
        self.assertEqual(self.client.get(reverse("delete_room", args=[room.id])).status_code, 405)
        self.assertTrue(Room.objects.filter(pk=room.pk).exists())
        self.client.post(reverse("delete_room", args=[room.id]))
        self.assertFalse(Room.objects.filter(pk=room.pk).exists())

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase

from listings.models import Profile, Room
from placements.models import Placement
from trust.models import FraudReport


class TenantUnreachableReportTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="landlord@example.com", email="landlord@example.com", password="password123"
        )
        Profile.objects.filter(user=self.landlord).update(role="landlord")

        self.tenant = User.objects.create_user(
            username="tenant@example.com", email="tenant@example.com", password="password123"
        )
        Profile.objects.filter(user=self.tenant).update(role="tenant")

        self.room = Room.objects.create(
            owner=self.landlord,
            title="Room A",
            description="A room",
            location="Joburg",
            suburb="Sandton",
            town="Johannesburg",
            city="Johannesburg",
            full_address="1 Main Street, Sandton",
            postal_code="2196",
            room_type="Single Room",
            contact_phone="0821234567",
            price=1500,
        )
        self.placement = Placement.objects.create(
            tenant=self.tenant,
            landlord=self.landlord,
            room=self.room,
            status=Placement.STATUS_MOVED_IN,
        )
        self.client = Client()

    def test_flag_tenant_unreachable_files_one_fraud_report(self):
        report = self.placement.flag_tenant_unreachable(reported_by=self.landlord)
        assert report is not None

        self.assertEqual(FraudReport.objects.count(), 1)
        self.assertEqual(report.category, FraudReport.CATEGORY_TENANT_UNREACHABLE)
        self.assertEqual(report.reported_user, self.tenant)

        self.placement.refresh_from_db()
        self.assertIsNotNone(self.placement.tenant_flagged_unreachable_at)

    def test_flag_tenant_unreachable_is_idempotent(self):
        self.placement.flag_tenant_unreachable(reported_by=self.landlord)
        second = self.placement.flag_tenant_unreachable(reported_by=self.landlord)

        self.assertIsNone(second)
        self.assertEqual(FraudReport.objects.count(), 1)

    def test_view_requires_moved_in_status(self):
        self.placement.status = Placement.STATUS_INTERESTED
        self.placement.save()

        self.client.login(username="landlord@example.com", password="password123")
        resp = self.client.post(
            f"/placements/landlord/{self.placement.id}/report-unreachable/"
        )

        self.assertRedirects(resp, "/placements/landlord/")
        self.assertEqual(FraudReport.objects.count(), 0)

    def test_view_files_report_for_moved_in_placement(self):
        self.client.login(username="landlord@example.com", password="password123")
        resp = self.client.post(
            f"/placements/landlord/{self.placement.id}/report-unreachable/"
        )

        self.assertRedirects(resp, "/placements/landlord/")
        self.assertEqual(FraudReport.objects.count(), 1)
        # FraudReport creation emails staff (trust/signals.py) - just
        # confirm that side-effect fired too.
        self.assertEqual(len(mail.outbox), 1)

    def test_other_landlord_cannot_report(self):
        other_landlord = User.objects.create_user(
            username="other@example.com", email="other@example.com", password="password123"
        )
        Profile.objects.filter(user=other_landlord).update(role="landlord")

        self.client.login(username="other@example.com", password="password123")
        resp = self.client.post(
            f"/placements/landlord/{self.placement.id}/report-unreachable/"
        )

        self.assertEqual(resp.status_code, 404)

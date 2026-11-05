from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.founding import FOUNDING_WAIVER_REASON
from accounts.models import Membership
from listings.models import Profile, Room
from placements.models import Placement, PlacementInvoice


class FoundingFirstTenantFreeTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="landlord@example.com", email="landlord@example.com", password="password123"
        )
        Profile.objects.filter(user=self.landlord).update(role="landlord")

        self.room = Room.objects.create(
            owner=self.landlord,
            title="Room A",
            description="A room",
            location="Tembisa",
            suburb="Ext 5",
            town="Tembisa",
            city="Johannesburg",
            full_address="1 Main Street, Tembisa",
            postal_code="1632",
            room_type="Backroom",
            contact_phone="0821234567",
            price=1500,
        )

    def set_founding(self, is_founding):
        membership, _ = Membership.objects.get_or_create(user=self.landlord)
        membership.is_founding = is_founding
        membership.save()

    def move_in(self, n):
        tenant = User.objects.create_user(username=f"tenant{n}@example.com", password="password123")
        placement = Placement.objects.create(
            tenant=tenant, landlord=self.landlord, room=self.room, status=Placement.STATUS_MOVED_IN
        )
        placement.mark_success_fee_due()
        placement.refresh_from_db()
        return placement

    def test_first_placement_is_waived_and_closed(self):
        self.set_founding(True)

        placement = self.move_in(1)

        self.assertEqual(placement.invoice.status, PlacementInvoice.STATUS_WAIVED)
        self.assertEqual(placement.invoice.waiver_reason, FOUNDING_WAIVER_REASON)
        self.assertEqual(placement.invoice.amount, Placement.calculate_success_fee(self.room.price))
        self.assertEqual(placement.status, Placement.STATUS_PAID)

    def test_only_the_first_placement_is_free(self):
        self.set_founding(True)
        self.move_in(1)

        second = self.move_in(2)

        self.assertEqual(second.invoice.status, PlacementInvoice.STATUS_PENDING)
        self.assertEqual(second.invoice.waiver_reason, "")
        self.assertEqual(second.status, Placement.STATUS_SUCCESS_FEE_DUE)

    @override_settings(FOUNDING_LANDLORD_SIGNUP_DEADLINE=date(2020, 1, 1))
    def test_non_founding_landlord_pays_as_normal(self):
        self.set_founding(False)

        placement = self.move_in(1)

        self.assertEqual(placement.invoice.status, PlacementInvoice.STATUS_PENDING)
        self.assertEqual(placement.status, Placement.STATUS_SUCCESS_FEE_DUE)

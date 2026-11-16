from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import founding
from accounts.models import Membership
from listings.models import Profile

PROGRAMME_CLOSED = override_settings(FOUNDING_LANDLORD_SIGNUP_DEADLINE=date(2020, 1, 1))


@override_settings(
    FOUNDING_LANDLORD_SIGNUP_DEADLINE=date(2099, 1, 31),
    FOUNDING_LANDLORD_FREE_UNTIL=date(2099, 4, 30),
)
class FoundingLandlordMembershipTests(TestCase):
    def make_landlord(self, username="landlord@example.com"):
        user = User.objects.create_user(username=username, email=username, password="password123")
        Profile.objects.filter(user=user).update(role="landlord")
        return user

    def test_new_membership_is_enrolled_while_programme_open(self):
        membership, _ = Membership.objects.get_or_create(user=self.make_landlord())

        self.assertTrue(membership.is_founding)
        self.assertIsNotNone(membership.founding_since)
        self.assertEqual(membership.tier, Membership.TIER_PRO)
        self.assertTrue(membership.on_pro_trial)
        self.assertTrue(membership.has_pro)
        self.assertEqual(membership.trial_end, founding.free_until())
        self.assertEqual(membership.founding_discount_percent, 50)
        self.assertTrue(membership.can_create_listing(50))

    def test_free_until_is_end_of_day_in_south_africa(self):
        end = founding.free_until().astimezone(founding.SAST)
        self.assertEqual((end.date(), end.hour, end.minute), (date(2099, 4, 30), 23, 59))

    @PROGRAMME_CLOSED
    def test_new_membership_after_deadline_is_free_with_unlimited_listings(self):
        membership = Membership.objects.create(user=self.make_landlord())

        self.assertFalse(membership.is_founding)
        self.assertEqual(membership.tier, Membership.TIER_FREE)
        self.assertFalse(membership.has_pro)
        self.assertEqual(membership.founding_discount_percent, 0)
        self.assertIsNone(membership.listing_limit())
        self.assertTrue(membership.can_create_listing(500))

    def test_enrol_existing_free_landlord_gets_pro_trial_and_price_lock(self):
        with PROGRAMME_CLOSED:
            membership = Membership.objects.create(user=self.make_landlord())

        self.assertTrue(membership.enrol_as_founding())
        membership.refresh_from_db()

        self.assertTrue(membership.is_founding)
        self.assertTrue(membership.on_pro_trial)
        self.assertEqual(membership.founding_discount_percent, 50)

    def test_enrol_keeps_a_paid_pro_period_as_is(self):
        with PROGRAMME_CLOSED:
            membership = Membership.objects.create(user=self.make_landlord())
        membership.extend_pro(band="small", cycle="monthly", months=1)
        paid_until = membership.paid_until

        self.assertTrue(membership.enrol_as_founding())
        membership.refresh_from_db()

        self.assertTrue(membership.is_founding)
        self.assertFalse(membership.is_trial)
        self.assertEqual(membership.paid_until, paid_until)
        self.assertEqual(membership.founding_discount_percent, 50)

    def test_enrol_skips_trust_and_safety_suspended_account(self):
        with PROGRAMME_CLOSED:
            suspended = Membership.objects.create(user=self.make_landlord("a@example.com"))
        suspended.user.is_active = False
        suspended.user.save()

        self.assertFalse(suspended.enrol_as_founding())
        self.assertFalse(Membership.objects.filter(is_founding=True).exists())

    def test_landlord_profile_shows_founding_badge(self):
        landlord = self.make_landlord()
        Membership.objects.get_or_create(user=landlord)

        resp = self.client.get(reverse("landlord_profile", args=[landlord.id]))

        self.assertContains(resp, "Founding Landlord")

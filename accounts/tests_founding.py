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
        # Same defaults every signup path passes to get_or_create.
        membership, _ = Membership.objects.get_or_create(
            user=self.make_landlord(),
            defaults={"tier": "starter", "is_trial": True, "trial_end": timezone.now() + timedelta(days=30)},
        )

        self.assertTrue(membership.is_founding)
        self.assertIsNotNone(membership.founding_since)
        self.assertEqual(membership.tier, "gold")
        self.assertEqual(membership.trial_end, founding.free_until())
        self.assertFalse(membership.is_trial_expired())
        self.assertTrue(membership.can_create_listing(50))

    def test_free_until_is_end_of_day_in_south_africa(self):
        end = founding.free_until().astimezone(founding.SAST)
        self.assertEqual((end.date(), end.hour, end.minute), (date(2099, 4, 30), 23, 59))

    @PROGRAMME_CLOSED
    def test_new_membership_after_deadline_gets_normal_trial(self):
        membership = Membership.objects.create(user=self.make_landlord())

        self.assertFalse(membership.is_founding)
        self.assertEqual(membership.tier, "starter")
        assert membership.trial_end is not None
        self.assertLess(membership.trial_end, timezone.now() + timedelta(days=31))

    def test_enrol_reactivates_expired_trial(self):
        with PROGRAMME_CLOSED:
            membership = Membership.objects.create(
                user=self.make_landlord(),
                trial_start=timezone.now() - timedelta(days=60),
            )
        membership.is_active = False
        membership.status = "suspended"
        membership.save()

        self.assertTrue(membership.enrol_as_founding())
        membership.refresh_from_db()

        self.assertTrue(membership.is_founding)
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.status, "active")
        self.assertEqual(membership.tier, "gold")
        self.assertTrue(membership.can_create_listing(10))

    def test_enrol_keeps_a_paid_plan_as_is(self):
        with PROGRAMME_CLOSED:
            membership = Membership.objects.create(user=self.make_landlord())
        membership.activate_membership(tier="bronze")

        self.assertTrue(membership.enrol_as_founding())
        membership.refresh_from_db()

        self.assertTrue(membership.is_founding)
        self.assertEqual(membership.tier, "bronze")
        self.assertFalse(membership.is_trial)

    def test_enrol_skips_suspended_account_and_pending_payment(self):
        with PROGRAMME_CLOSED:
            suspended = Membership.objects.create(user=self.make_landlord("a@example.com"))
            pending = Membership.objects.create(user=self.make_landlord("b@example.com"))
        suspended.user.is_active = False
        suspended.user.save()
        pending.status = "pending"
        pending.save()

        self.assertFalse(suspended.enrol_as_founding())
        self.assertFalse(pending.enrol_as_founding())
        self.assertFalse(Membership.objects.filter(is_founding=True).exists())

    def test_landlord_profile_shows_founding_badge(self):
        landlord = self.make_landlord()
        Membership.objects.get_or_create(user=landlord)

        resp = self.client.get(reverse("landlord_profile", args=[landlord.id]))

        self.assertContains(resp, "Founding Landlord")

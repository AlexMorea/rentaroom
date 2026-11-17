from datetime import date, timedelta
from decimal import Decimal
from unittest import mock
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership
from listings.models import Profile, Room

from . import payfast, pricing
from .boosts import featured_room_ids, pro_credits_left
from .models import Boost, Payment

PAYFAST = override_settings(
    PAYFAST_MERCHANT_ID="10000100",
    PAYFAST_MERCHANT_KEY="46f0cd694581a",
    PAYFAST_PASSPHRASE="test-passphrase",
    PAYFAST_SANDBOX=True,
    PAYFAST_SITE_URL="https://example.test",
)
PROGRAMME_CLOSED = override_settings(FOUNDING_LANDLORD_SIGNUP_DEADLINE=date(2020, 1, 1))


def make_landlord(username="landlord@example.com"):
    user = User.objects.create_user(username=username, email=username, password="password123")
    Profile.objects.filter(user=user).update(role="landlord")
    return user


def make_room(owner, title="Room A", units=1, **extra):
    return Room.objects.create(
        owner=owner, title=title, description="A room", location="Tembisa", suburb="Ext 5",
        town="Tembisa", city="Johannesburg", full_address="1 Main Street, Tembisa",
        postal_code="1632", room_type="Backroom", contact_phone="0821234567", price=1500,
        total_units=units, available_units=units, **extra,
    )


def signed_itn(fields: dict) -> str:
    """Builds an ITN body exactly the way PayFast signs it."""
    pairs = list(fields.items())
    signature = payfast._md5(payfast._with_passphrase(payfast.itn_param_string(pairs)))
    return urlencode([*pairs, ("signature", signature)])


class PricingTests(TestCase):
    def test_bands_by_room_count(self):
        self.assertEqual(pricing.band_for_rooms(0).code, "small")
        self.assertEqual(pricing.band_for_rooms(5).code, "small")
        self.assertEqual(pricing.band_for_rooms(6).code, "medium")
        self.assertEqual(pricing.band_for_rooms(15).code, "medium")
        self.assertEqual(pricing.band_for_rooms(16).code, "large")

    def test_prices(self):
        small, medium, large = pricing.PRO_BANDS
        self.assertEqual(pricing.pro_price(small, "monthly"), Decimal(99))
        self.assertEqual(pricing.pro_price(medium, "annual"), Decimal(1990))
        # Founding 50%: rounded down to whole rands, landlord's favour.
        self.assertEqual(pricing.pro_price(small, "monthly", 50), Decimal(49))
        self.assertEqual(pricing.pro_price(large, "monthly", 50), Decimal(174))

    def test_rooms_count_units_not_listings(self):
        landlord = make_landlord()
        make_room(landlord, "A", units=4)
        make_room(landlord, "B", units=3)
        self.assertEqual(pricing.room_count_for(landlord), 7)


class CheckoutSigningTests(TestCase):
    @PAYFAST
    def test_fields_are_ordered_and_signed(self):
        fields = payfast.checkout_fields({
            "amount": "99.00", "item_name": "Pro", "m_payment_id": "R4Y-1", "name_last": "",
        })
        names = [name for name, _ in fields]
        self.assertEqual(names[:2], ["merchant_id", "merchant_key"])
        self.assertLess(names.index("m_payment_id"), names.index("amount"))
        self.assertNotIn("name_last", names)  # blank values are dropped
        self.assertEqual(names[-1], "signature")
        self.assertEqual(len(dict(fields)["signature"]), 32)

    @PAYFAST
    def test_passphrase_changes_signature(self):
        first = dict(payfast.checkout_fields({"amount": "1.00", "item_name": "x"}))["signature"]
        with override_settings(PAYFAST_PASSPHRASE="other"):
            second = dict(payfast.checkout_fields({"amount": "1.00", "item_name": "x"}))["signature"]
        self.assertNotEqual(first, second)


@PAYFAST
@PROGRAMME_CLOSED
class ProCheckoutAndNotifyTests(TestCase):
    def setUp(self):
        self.landlord = make_landlord()
        make_room(self.landlord, units=3)
        self.client.force_login(self.landlord)
        self.membership, _ = Membership.objects.get_or_create(user=self.landlord)

    def checkout(self, cycle="monthly"):
        resp = self.client.post(reverse("billing:pro_checkout"), {"cycle": cycle})
        self.assertEqual(resp.status_code, 200)
        return Payment.objects.latest("pk")

    def notify(self, payment, **overrides):
        fields = {
            "m_payment_id": payment.m_payment_id,
            "pf_payment_id": "1001",
            "payment_status": "COMPLETE",
            "item_name": payment.item_name,
            "amount_gross": f"{payment.amount:.2f}",
            "amount_fee": "-3.50",
            "amount_net": f"{payment.amount - Decimal('3.50'):.2f}",
            "merchant_id": "10000100",
            "token": "tok-abc",
            **overrides,
        }
        with mock.patch("billing.payfast.itn_confirmed_by_payfast", return_value=True):
            return self.client.post(
                reverse("billing:payfast_notify"), signed_itn(fields),
                content_type="application/x-www-form-urlencoded",
            )

    def test_checkout_creates_pending_payment_at_band_price(self):
        payment = self.checkout()
        self.assertEqual(payment.status, Payment.STATUS_PENDING)
        self.assertEqual(payment.amount, Decimal(99))
        self.assertEqual(payment.pro_band, "small")

    def test_checkout_page_posts_signed_form_to_payfast_sandbox(self):
        resp = self.client.post(reverse("billing:pro_checkout"), {"cycle": "annual"})
        self.assertContains(resp, "https://sandbox.payfast.co.za/eng/process")
        self.assertContains(resp, 'name="signature"')
        self.assertContains(resp, 'name="subscription_type" value="1"')
        self.assertContains(resp, 'name="frequency" value="6"')
        self.assertEqual(Payment.objects.get().amount, Decimal(990))

    def test_verified_notification_activates_pro(self):
        payment = self.checkout()
        self.assertEqual(self.notify(payment).status_code, 200)

        payment.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_COMPLETE)
        self.assertTrue(self.membership.has_pro)
        self.assertTrue(self.membership.auto_renew)
        self.assertEqual(self.membership.payfast_token, "tok-abc")
        assert self.membership.paid_until is not None
        self.assertGreater(self.membership.paid_until, timezone.now() + timedelta(days=27))

    def test_resent_notification_is_applied_once(self):
        payment = self.checkout()
        self.notify(payment)
        self.membership.refresh_from_db()
        first_until = self.membership.paid_until

        self.notify(payment)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.paid_until, first_until)
        self.assertEqual(Payment.objects.filter(status=Payment.STATUS_COMPLETE).count(), 1)

    def test_monthly_debit_extends_pro(self):
        payment = self.checkout()
        self.notify(payment)
        self.membership.refresh_from_db()
        first_until = self.membership.paid_until

        self.notify(payment, pf_payment_id="1002")
        self.membership.refresh_from_db()
        assert first_until is not None and self.membership.paid_until is not None
        self.assertGreater(self.membership.paid_until, first_until + timedelta(days=27))
        self.assertEqual(payment.renewals.count(), 1)

    def test_bad_signature_is_rejected(self):
        payment = self.checkout()
        body = signed_itn({"m_payment_id": payment.m_payment_id, "payment_status": "COMPLETE",
                           "amount_gross": "99.00", "merchant_id": "10000100"})
        body = body.replace("amount_gross=99.00", "amount_gross=1.00")
        resp = self.client.post(reverse("billing:payfast_notify"), body,
                                content_type="application/x-www-form-urlencoded")
        self.assertEqual(resp.status_code, 400)
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.has_pro)

    def test_unconfirmed_by_payfast_is_rejected(self):
        payment = self.checkout()
        body = signed_itn({"m_payment_id": payment.m_payment_id, "payment_status": "COMPLETE",
                           "amount_gross": "99.00", "merchant_id": "10000100"})
        with mock.patch("billing.payfast.itn_confirmed_by_payfast", return_value=False):
            resp = self.client.post(reverse("billing:payfast_notify"), body,
                                    content_type="application/x-www-form-urlencoded")
        self.assertEqual(resp.status_code, 400)

    def test_wrong_amount_does_not_activate(self):
        payment = self.checkout()
        self.notify(payment, amount_gross="1.00")
        payment.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_FAILED)
        self.assertFalse(self.membership.has_pro)

    def test_return_url_alone_changes_nothing(self):
        payment = self.checkout()
        self.client.get(reverse("billing:payment_return", args=[payment.pk]))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PENDING)

    def test_cancelled_subscription_stops_auto_renew_but_keeps_paid_period(self):
        payment = self.checkout()
        self.notify(payment)
        self.notify(payment, payment_status="CANCELLED", pf_payment_id="")
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.auto_renew)
        self.assertTrue(self.membership.has_pro)

    def test_cancellation_is_accepted_without_payfast_validation(self):
        # PayFast's validate endpoint says "not valid" for cancellations.
        payment = self.checkout()
        self.notify(payment)
        fields = {"m_payment_id": payment.m_payment_id, "payment_status": "CANCELLED",
                  "token": "tok-abc", "merchant_id": "10000100"}
        with mock.patch("billing.payfast.itn_confirmed_by_payfast", return_value=False):
            resp = self.client.post(reverse("billing:payfast_notify"), signed_itn(fields),
                                    content_type="application/x-www-form-urlencoded")
        self.assertEqual(resp.status_code, 200)
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.auto_renew)
        self.assertTrue(self.membership.has_pro)

    def test_cancellation_matched_by_token_alone(self):
        self.notify(self.checkout())
        fields = {"payment_status": "CANCELLED", "token": "tok-abc"}
        with mock.patch("billing.payfast.itn_confirmed_by_payfast", return_value=False):
            resp = self.client.post(reverse("billing:payfast_notify"), signed_itn(fields),
                                    content_type="application/x-www-form-urlencoded")
        self.assertEqual(resp.status_code, 200)
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.auto_renew)

    def test_unsigned_cancellation_is_rejected(self):
        self.notify(self.checkout())
        body = urlencode({"payment_status": "CANCELLED", "token": "tok-abc", "signature": "nope"})
        resp = self.client.post(reverse("billing:payfast_notify"), body,
                                content_type="application/x-www-form-urlencoded")
        self.assertEqual(resp.status_code, 400)
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.auto_renew)

    def test_payment_still_needs_payfast_validation(self):
        payment = self.checkout()
        fields = {"m_payment_id": payment.m_payment_id, "pf_payment_id": "9", "payment_status": "COMPLETE",
                  "amount_gross": "99.00", "merchant_id": "10000100"}
        with mock.patch("billing.payfast.itn_confirmed_by_payfast", return_value=False):
            resp = self.client.post(reverse("billing:payfast_notify"), signed_itn(fields),
                                    content_type="application/x-www-form-urlencoded")
        self.assertEqual(resp.status_code, 400)
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.has_pro)

    def test_cancel_button_calls_payfast(self):
        self.notify(self.checkout())
        with mock.patch("billing.payfast.cancel_subscription", return_value=True) as cancel:
            self.client.post(reverse("billing:cancel_pro"))
        cancel.assert_called_once_with("tok-abc")
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.auto_renew)


@PAYFAST
@override_settings(FOUNDING_LANDLORD_SIGNUP_DEADLINE=date(2099, 1, 31), FOUNDING_LANDLORD_FREE_UNTIL=date(2099, 4, 30))
class FoundingPricingTests(TestCase):
    def setUp(self):
        self.landlord = make_landlord()
        make_room(self.landlord)
        self.client.force_login(self.landlord)
        self.membership, _ = Membership.objects.get_or_create(user=self.landlord)

    def test_nothing_to_pay_during_founding_trial(self):
        self.client.post(reverse("billing:pro_checkout"), {"cycle": "monthly"})
        self.assertFalse(Payment.objects.exists())

    def test_locked_price_applies_after_trial(self):
        self.membership.trial_end = timezone.now() - timedelta(days=1)
        self.membership.save()
        self.client.post(reverse("billing:pro_checkout"), {"cycle": "monthly"})
        self.assertEqual(Payment.objects.get().amount, Decimal(49))

    def test_lock_is_lost_after_paid_pro_lapses_past_grace(self):
        self.membership.is_trial = False
        self.membership.paid_until = timezone.now() - timedelta(days=pricing.FOUNDING_LOCK_GRACE_DAYS + 1)
        self.membership.save()
        self.assertEqual(self.membership.current_discount_percent, 0)

    def test_plans_page_shows_locked_price(self):
        resp = self.client.get(reverse("membership"))
        self.assertContains(resp, "50% off Pro for life")
        self.assertContains(resp, "R49")


@PROGRAMME_CLOSED
class LapseTests(TestCase):
    def test_expired_pro_drops_to_free_and_can_still_list(self):
        landlord = make_landlord()
        membership, _ = Membership.objects.get_or_create(user=landlord)
        membership.tier = Membership.TIER_PRO
        membership.is_trial = True
        membership.trial_end = timezone.now() - timedelta(days=1)
        membership.save()

        self.client.force_login(landlord)
        self.client.get(reverse("dashboard"))  # middleware runs

        membership.refresh_from_db()
        self.assertEqual(membership.tier, Membership.TIER_FREE)
        self.assertTrue(membership.is_active)
        self.assertTrue(membership.can_create_listing(100))
        self.assertEqual(self.client.get(reverse("create_room")).status_code, 200)


@PAYFAST
@PROGRAMME_CLOSED
@override_settings(BOOSTS_ENABLED=True)
class BoostTests(TestCase):
    def setUp(self):
        self.landlord = make_landlord()
        self.room = make_room(self.landlord)
        self.client.force_login(self.landlord)
        self.membership, _ = Membership.objects.get_or_create(user=self.landlord)

    def give_pro(self):
        self.membership.extend_pro(band="small", cycle="monthly", months=1)

    @override_settings(BOOSTS_ENABLED=False)
    def test_boosts_closed_until_tenant_launch(self):
        resp = self.client.get(reverse("billing:boost_room", args=[self.room.pk]))
        self.assertContains(resp, "Boosts open when Rooms4You launches to tenants.")
        self.client.post(reverse("billing:boost_room", args=[self.room.pk]), {"option": "week"})
        self.assertFalse(Payment.objects.exists())

    def test_stale_or_full_rooms_cannot_be_boosted(self):
        self.room.last_confirmed_at = timezone.now() - timedelta(days=60)
        self.room.save()
        self.client.post(reverse("billing:boost_room", args=[self.room.pk]), {"option": "week"})
        self.assertFalse(Payment.objects.exists())

    def test_pro_gets_two_free_boosts_a_month(self):
        self.give_pro()
        url = reverse("billing:boost_room", args=[self.room.pk])
        for _ in range(3):
            self.client.post(url, {"option": "pro_credit"})
        self.assertEqual(Boost.objects.filter(source=Boost.SOURCE_PRO_CREDIT).count(), 2)
        self.assertEqual(pro_credits_left(self.membership), 0)

    def test_second_boost_extends_instead_of_overlapping(self):
        self.give_pro()
        url = reverse("billing:boost_room", args=[self.room.pk])
        self.client.post(url, {"option": "pro_credit"})
        self.client.post(url, {"option": "pro_credit"})
        first, second = Boost.objects.order_by("starts_at")
        self.assertEqual(second.starts_at, first.ends_at)

    def test_paid_boost_goes_live_on_verified_payment(self):
        self.client.post(reverse("billing:boost_room", args=[self.room.pk]), {"option": "week"})
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal(29))
        self.assertFalse(Boost.objects.exists())

        fields = {"m_payment_id": payment.m_payment_id, "pf_payment_id": "2001",
                  "payment_status": "COMPLETE", "amount_gross": "29.00", "merchant_id": "10000100"}
        with mock.patch("billing.payfast.itn_confirmed_by_payfast", return_value=True):
            self.client.post(reverse("billing:payfast_notify"), signed_itn(fields),
                             content_type="application/x-www-form-urlencoded")

        boost = Boost.objects.get()
        self.assertEqual(boost.source, Boost.SOURCE_PAID)
        self.assertTrue(boost.is_active)
        self.assertAlmostEqual((boost.ends_at - boost.starts_at).days, 7)

    def test_featured_slots_are_capped(self):
        rooms = [make_room(self.landlord, f"R{i}") for i in range(5)]
        now = timezone.now()
        for room in rooms:
            Boost.objects.create(room=room, landlord=self.landlord, source=Boost.SOURCE_STAFF,
                                 starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=1))
        ids = [r.pk for r in rooms] + [self.room.pk]
        featured = featured_room_ids(ids)
        self.assertEqual(len(featured), pricing.FEATURED_SLOTS)
        self.assertNotIn(self.room.pk, featured)

    def test_boosted_room_is_pinned_and_labelled_in_search(self):
        other = make_room(self.landlord, "Popular room")
        Room.objects.filter(pk=other.pk).update(score=999)
        now = timezone.now()
        Boost.objects.create(room=self.room, landlord=self.landlord, source=Boost.SOURCE_STAFF,
                             starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=1))

        resp = self.client.get(reverse("room_list"))
        rooms = list(resp.context["rooms"])
        self.assertEqual(rooms[0].pk, self.room.pk)
        self.assertContains(resp, "⭐ Featured")

    def test_expired_boost_is_not_featured(self):
        now = timezone.now()
        Boost.objects.create(room=self.room, landlord=self.landlord, source=Boost.SOURCE_STAFF,
                             starts_at=now - timedelta(days=8), ends_at=now - timedelta(days=1))
        self.assertEqual(featured_room_ids([self.room.pk]), [])


class MigrationTests(TestCase):
    """Runs the Free/Pro data migration's forwards() against live rows."""

    def run_forwards(self):
        import importlib

        from django.apps import apps

        module = importlib.import_module("accounts.migrations.0007_move_to_free_and_pro")
        module.forwards(apps, None)

    @PROGRAMME_CLOSED
    def test_moves_landlords_onto_new_plans(self):
        expired = Membership.objects.create(user=make_landlord("a@example.com"))
        Membership.objects.filter(pk=expired.pk).update(tier="starter", is_active=False, status="suspended")

        banned = Membership.objects.create(user=make_landlord("b@example.com"))
        Membership.objects.filter(pk=banned.pk).update(tier="starter", is_active=False, status="suspended")
        User.objects.filter(pk=banned.user_id).update(is_active=False)

        founder = Membership.objects.create(user=make_landlord("c@example.com"))
        Membership.objects.filter(pk=founder.pk).update(tier="gold", is_founding=True, is_trial=True)

        self.run_forwards()

        expired.refresh_from_db()
        banned.refresh_from_db()
        founder.refresh_from_db()
        self.assertEqual((expired.tier, expired.is_active, expired.status), ("free", True, "active"))
        self.assertEqual((banned.tier, banned.is_active, banned.status), ("free", False, "suspended"))
        self.assertEqual(founder.tier, "pro")
        self.assertTrue(founder.on_pro_trial)
        self.assertEqual(founder.founding_discount_percent, 50)


class AdminPagesLoadTests(TestCase):
    """Every billing-related admin page must render (a stray % in an
    action description once crashed the Memberships list)."""

    def test_admin_pages(self):
        staff = User.objects.create_superuser("staff", "staff@example.com", "password123")
        landlord = make_landlord()
        membership, _ = Membership.objects.get_or_create(user=landlord)
        room = make_room(landlord)
        payment = Payment.objects.create(user=landlord, kind=Payment.KIND_BOOST, amount=29, item_name="x", room=room)
        boost = Boost.objects.create(room=room, landlord=landlord, source=Boost.SOURCE_STAFF,
                                     starts_at=timezone.now(), ends_at=timezone.now() + timedelta(days=1))
        self.client.force_login(staff)
        for url in [
            reverse("admin:accounts_membership_changelist"),
            reverse("admin:accounts_membership_change", args=[membership.pk]),
            reverse("admin:billing_payment_changelist"),
            reverse("admin:billing_payment_change", args=[payment.pk]),
            reverse("admin:billing_boost_changelist"),
            reverse("admin:billing_boost_change", args=[boost.pk]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_membership_admin_actions(self):
        staff = User.objects.create_superuser("staff", "staff@example.com", "password123")
        landlord = make_landlord()
        membership, _ = Membership.objects.get_or_create(user=landlord)
        self.client.force_login(staff)
        url = reverse("admin:accounts_membership_changelist")
        self.client.post(url, {"action": "grant_one_month_pro", "_selected_action": [membership.pk]})
        membership.refresh_from_db()
        self.assertTrue(membership.on_paid_pro)
        self.assertEqual(Payment.objects.filter(user=landlord, amount=0).count(), 1)

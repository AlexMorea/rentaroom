from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import monetisation
from .models import (
    AdCampaign,
    AdImpression,
    Earning,
    FundTopUp,
    Like,
    Payout,
    PayoutPeriod,
    Video,
    View,
)
from .templatetags.shaya_tags import rands

TZ = timezone.get_current_timezone()
SEPT = timezone.make_aware(datetime(2026, 9, 15, 12), TZ)


def make_creator(username, verified=True):
    user = User.objects.create_user(username, password="pw-123456789")
    p = user.profile
    if verified:
        p.date_of_birth = date(1995, 1, 1)
        p.id_verified = True
        p.payout_shap_id = "0821234567@bank"
    p.save()
    return user


def make_video(creator, caption="clip"):
    return Video.objects.create(
        creator=creator,
        caption=caption,
        file=SimpleUploadedFile("c.mp4", b"\x00" * 10, content_type="video/mp4"),
    )


def add_views(video, n, when=SEPT, prefix="v"):
    View.objects.bulk_create(
        [
            View(video=video, viewer_key=f"{prefix}{video.pk}-{i}", watch_ms=5000,
                 qualified=True, created_at=when)
            for i in range(n)
        ]
    )


@override_settings(MEDIA_ROOT="/tmp/shaya-test-media")
class ViewQualificationTests(TestCase):
    def setUp(self):
        self.creator = make_creator("thandi")
        self.video = make_video(self.creator)

    def test_short_watch_does_not_qualify(self):
        v = monetisation.record_view(self.video, None, "k1", 1500)
        self.assertFalse(v.qualified)

    def test_real_watch_qualifies_once_per_day(self):
        first = monetisation.record_view(self.video, None, "k1", 4000, now=SEPT)
        again = monetisation.record_view(self.video, None, "k1", 4000, now=SEPT + timedelta(hours=2))
        next_day = monetisation.record_view(self.video, None, "k1", 4000, now=SEPT + timedelta(hours=25))
        self.assertEqual([first.qualified, again.qualified, next_day.qualified], [True, False, True])

    def test_creator_watching_own_clip_never_qualifies(self):
        v = monetisation.record_view(self.video, self.creator, "k-self", 60000)
        self.assertFalse(v.qualified)

    def test_watch_time_is_capped(self):
        v = monetisation.record_view(self.video, None, "k1", 10**9)
        self.assertEqual(v.watch_ms, 180_000)

    def test_beacon_endpoint(self):
        url = reverse("view_beacon", args=[self.video.pk])
        r = self.client.post(url, data='{"watch_ms": 5000}', content_type="application/json")
        self.assertEqual(r.json(), {"qualified": True})
        r = self.client.post(url, data='{"watch_ms": 5000}', content_type="application/json")
        self.assertEqual(r.json(), {"qualified": False})
        r = self.client.post(url, data='{"watch_ms": "lots"}', content_type="application/json")
        self.assertEqual(r.status_code, 400)


@override_settings(MEDIA_ROOT="/tmp/shaya-test-media")
class PayoutMathsTests(TestCase):
    def setUp(self):
        self.a = make_creator("a")
        self.b = make_creator("b")
        self.c = make_creator("c")
        self.unverified = make_creator("minor", verified=False)
        self.va = make_video(self.a)
        self.vb = make_video(self.b)
        self.vc = make_video(self.c)
        self.vu = make_video(self.unverified)
        add_views(self.va, 3000)
        add_views(self.vb, 1000)
        add_views(self.vc, 999)  # one short of the threshold
        add_views(self.vu, 5000)  # not eligible to earn
        ad = AdCampaign.objects.create(
            advertiser="Spaza", video=self.va, cpm_cents=3000, budget_cents=10**7
        )
        # 10,000 impressions at R30 CPM = R300 of ad revenue.
        AdImpression.objects.bulk_create(
            [AdImpression(campaign=ad, viewer_key="x", cost_millicents=3000, created_at=SEPT)]
            * 10_000
        )
        FundTopUp.objects.create(month=date(2026, 9, 1), source="Sponsor", amount_cents=50_000)

    def test_close_month(self):
        period = monetisation.close_month(date(2026, 9, 1))
        self.assertEqual(period.ad_revenue_cents, 30_000)
        # 55% of R300 + R500 top-up = R665
        self.assertEqual(period.creator_pool_cents, 66_500)
        self.assertEqual(period.paid_views, 4000)
        earnings = {e.creator.username: e.amount_cents for e in period.earnings.all()}
        self.assertEqual(earnings, {"a": 49_875, "b": 16_625})
        self.assertEqual(sum(earnings.values()), period.creator_pool_cents)

    def test_close_month_is_idempotent(self):
        monetisation.close_month(date(2026, 9, 1))
        monetisation.close_month(date(2026, 9, 1))
        self.assertEqual(Earning.objects.count(), 2)

    def test_other_months_views_ignored(self):
        add_views(self.vb, 5000, when=SEPT + timedelta(days=30), prefix="oct")
        period = monetisation.close_month(date(2026, 9, 1))
        self.assertEqual(period.paid_views, 4000)

    def test_split_always_sums_to_pool(self):
        shares = monetisation.split_pool(100, {1: 1, 2: 1, 3: 1})
        self.assertEqual(sum(shares.values()), 100)
        self.assertEqual(sorted(shares.values()), [33, 33, 34])

    def test_withdraw(self):
        monetisation.close_month(date(2026, 9, 1))
        self.client.force_login(self.a)
        self.client.post(reverse("withdraw"))
        payout = Payout.objects.get(creator=self.a)
        self.assertEqual(payout.amount_cents, 49_875)
        self.assertTrue(payout.reference.startswith("SHAYA"))
        self.assertEqual(monetisation.balance_cents(self.a), 0)
        # Second tap: nothing left, no second payout.
        self.client.post(reverse("withdraw"))
        self.assertEqual(Payout.objects.filter(creator=self.a).count(), 1)

    def test_withdraw_below_minimum_refused(self):
        PayoutPeriod.objects.create(month=date(2026, 8, 1), closed_at=timezone.now())
        Earning.objects.create(
            period=PayoutPeriod.objects.get(month=date(2026, 8, 1)),
            creator=self.c, paid_views=10, amount_cents=1000,
        )
        with self.assertRaises(monetisation.PayoutError):
            monetisation.request_payout(self.c)


@override_settings(MEDIA_ROOT="/tmp/shaya-test-media")
class AdTests(TestCase):
    def setUp(self):
        self.creator = make_creator("ads")
        self.video = make_video(self.creator)
        self.campaign = AdCampaign.objects.create(
            advertiser="Spaza", video=self.video, cpm_cents=850, budget_cents=1
        )

    def test_fractional_cent_cpm_is_not_lost(self):
        monetisation.charge_impression(self.campaign, "k")
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.spent_millicents, 850)
        self.assertTrue(self.campaign.active)

    def test_campaign_stops_when_budget_spent(self):
        monetisation.charge_impression(self.campaign, "k1")
        monetisation.charge_impression(self.campaign, "k2")
        self.campaign.refresh_from_db()
        self.assertFalse(self.campaign.active)

    def test_impression_charged_once_per_viewer_per_hour(self):
        url = reverse("ad_impression", args=[self.campaign.pk])
        self.assertTrue(self.client.post(url).json()["charged"])
        self.assertFalse(self.client.post(url).json()["charged"])
        self.assertEqual(AdImpression.objects.count(), 1)

    def test_feed_inserts_sponsored_clip(self):
        self.campaign.budget_cents = 10_000
        self.campaign.save()
        for i in range(4):
            make_video(self.creator, caption=f"organic {i}")
        with self.settings(SHAYA={**settings.SHAYA, "AD_EVERY_N_CLIPS": 2}):
            r = self.client.get(reverse("feed"))
        self.assertContains(r, "Sponsored · Spaza", count=1)


@override_settings(MEDIA_ROOT="/tmp/shaya-test-media")
class PageTests(TestCase):
    def setUp(self):
        self.creator = make_creator("lerato")
        self.video = make_video(self.creator, caption="Taxi rank comedy #mzansi")

    def test_pages_render(self):
        for url in [
            reverse("feed"),
            reverse("feed") + "?q=taxi&lang=en",
            reverse("video_detail", args=[self.video.pk]),
            reverse("profile", args=["lerato"]),
            reverse("about"),
            reverse("signup"),
            reverse("login"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_removed_video_hidden(self):
        self.video.is_removed = True
        self.video.save()
        self.assertNotContains(self.client.get(reverse("feed")), "Taxi rank")
        self.assertEqual(self.client.get(reverse("video_detail", args=[self.video.pk])).status_code, 404)

    def test_like_toggle(self):
        fan = make_creator("fan")
        self.client.force_login(fan)
        url = reverse("toggle_like", args=[self.video.pk])
        self.assertEqual(self.client.post(url).json(), {"liked": True, "count": 1})
        self.assertEqual(self.client.post(url).json(), {"liked": False, "count": 0})
        self.assertFalse(Like.objects.exists())

    def test_dashboard(self):
        self.client.force_login(self.creator)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Creator studio")
        self.assertContains(r, "Road to 1000")

    def test_signup_rejects_under_13(self):
        r = self.client.post(reverse("signup"), {
            "username": "kid", "password1": "Very-long-pw-1", "password2": "Very-long-pw-1",
            "date_of_birth": (date.today() - timedelta(days=365 * 10)).isoformat(),
        })
        self.assertFalse(User.objects.filter(username="kid").exists())
        self.assertContains(r, "13 and older")

    def test_upload_rejects_non_video(self):
        self.client.force_login(self.creator)
        r = self.client.post(reverse("upload"), {
            "file": SimpleUploadedFile("x.exe", b"MZ"), "caption": "x", "language": "en",
        })
        self.assertContains(r, "Upload an MP4")


class RandsFilterTests(TestCase):
    def test_format(self):
        self.assertEqual(rands(123456), "R1 234.56")
        self.assertEqual(rands(5), "R0.05")

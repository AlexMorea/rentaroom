"""How views turn into Rands.

The model is a monthly revenue-share pool, the same shape as YouTube's
Partner Programme and TikTok's Creator Rewards:

1. Every ad impression in the feed is charged to an advertiser at their CPM.
2. At month end, CREATOR_SHARE_BPS of that ad revenue, plus any sponsor or
   grant top-ups, becomes the creator pool.
3. The pool is split across creators in proportion to their *paid views*:
   qualified views in that month, on videos that have passed the
   1,000-view threshold, by creators who are eligible to earn.

Everything is integer cents, and the split uses the largest-remainder
method so the creator payouts always add up to exactly the pool.
"""
import hashlib
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from .models import (
    AdCampaign,
    AdImpression,
    Earning,
    FundTopUp,
    Payout,
    PayoutPeriod,
    View,
)


def conf(key):
    return settings.SHAYA[key]


def viewer_key_for(request):
    """Stable, non-reversible identifier for de-duplicating views."""
    if request.user.is_authenticated:
        raw = f"user:{request.user.pk}"
    else:
        if not request.session.session_key:
            request.session.save()
        raw = f"session:{request.session.session_key}"
    return hashlib.sha256(f"{settings.SECRET_KEY}:{raw}".encode()).hexdigest()


def record_view(video, viewer, viewer_key, watch_ms, now=None):
    """Log a playback and decide whether it is a paid ("qualified") view.

    A view qualifies when the person actually watched (>= QUALIFIED_WATCH_MS),
    is not the creator, and has not already had a qualified view of this
    video inside the de-duplication window.
    """
    now = now or timezone.now()
    watch_ms = max(0, min(int(watch_ms), conf("MAX_DURATION_SECONDS") * 1000))
    is_creator = viewer is not None and viewer.pk == video.creator_id
    qualified = watch_ms >= conf("QUALIFIED_WATCH_MS") and not is_creator
    if qualified:
        window_start = now - timedelta(hours=conf("VIEW_DEDUPE_HOURS"))
        qualified = not View.objects.filter(
            video=video,
            viewer_key=viewer_key,
            qualified=True,
            created_at__gte=window_start,
        ).exists()
    return View.objects.create(
        video=video,
        viewer=viewer,
        viewer_key=viewer_key,
        watch_ms=watch_ms,
        qualified=qualified,
        created_at=now,
    )


def pick_campaign(exclude_ids=()):
    """Choose the active campaign with the most budget left, if any."""
    candidates = [
        c
        for c in AdCampaign.objects.filter(active=True, video__is_removed=False)
        .exclude(pk__in=exclude_ids)
        .select_related("video", "video__creator")
        if c.remaining_cents > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.remaining_cents)


@transaction.atomic
def charge_impression(campaign, viewer_key, now=None):
    cost = campaign.cost_per_impression_millicents
    AdImpression.objects.create(
        campaign=campaign,
        viewer_key=viewer_key,
        cost_millicents=cost,
        created_at=now or timezone.now(),
    )
    AdCampaign.objects.filter(pk=campaign.pk).update(
        spent_millicents=F("spent_millicents") + cost
    )
    campaign.refresh_from_db(fields=["spent_millicents"])
    if campaign.remaining_cents <= 0:
        AdCampaign.objects.filter(pk=campaign.pk).update(active=False)


def month_bounds(month):
    start = month.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1)
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(timezone.datetime(start.year, start.month, 1), tz),
        timezone.make_aware(timezone.datetime(end.year, end.month, 1), tz),
    )


def monetised_video_ids(up_to):
    """Videos with at least the threshold of qualified views before `up_to`."""
    return set(
        View.objects.filter(qualified=True, created_at__lt=up_to)
        .values("video")
        .annotate(n=Count("id"))
        .filter(n__gte=conf("MONETISE_THRESHOLD_VIEWS"))
        .values_list("video", flat=True)
    )


def split_pool(pool_cents, weights):
    """Largest-remainder split of an integer pool by integer weights."""
    total = sum(weights.values())
    if not total or not pool_cents:
        return {k: 0 for k in weights}
    shares = {}
    remainders = []
    for key, w in weights.items():
        exact = pool_cents * w
        shares[key] = exact // total
        remainders.append((exact % total, key))
    leftover = pool_cents - sum(shares.values())
    for _, key in sorted(remainders, key=lambda r: (-r[0], str(r[1])))[:leftover]:
        shares[key] += 1
    return shares


@transaction.atomic
def close_month(month):
    """Calculate and lock every creator's earnings for `month`.

    Idempotent: closing an already-closed month returns it unchanged.
    """
    month = month.replace(day=1)
    period, _ = PayoutPeriod.objects.select_for_update().get_or_create(month=month)
    if period.closed_at:
        return period

    start, end = month_bounds(month)
    ad_millicents = (
        AdImpression.objects.filter(created_at__gte=start, created_at__lt=end)
        .aggregate(total=Sum("cost_millicents"))["total"]
        or 0
    )
    ad_cents = ad_millicents // 1000
    top_up = FundTopUp.objects.filter(month=month).aggregate(t=Sum("amount_cents"))["t"] or 0
    pool = ad_cents * conf("CREATOR_SHARE_BPS") // 10000 + top_up

    eligible_videos = monetised_video_ids(end)
    views_by_creator = defaultdict(int)
    rows = (
        View.objects.filter(
            qualified=True,
            created_at__gte=start,
            created_at__lt=end,
            video_id__in=eligible_videos,
        )
        .values("video__creator")
        .annotate(n=Count("id"))
    )
    User = get_user_model()
    creators = {
        u.pk: u
        for u in User.objects.filter(
            pk__in=[r["video__creator"] for r in rows]
        ).select_related("profile")
    }
    for r in rows:
        creator = creators[r["video__creator"]]
        profile = getattr(creator, "profile", None)
        if profile and profile.can_earn:
            views_by_creator[creator.pk] += r["n"]

    shares = split_pool(pool, views_by_creator)
    for creator_id, amount in shares.items():
        Earning.objects.create(
            period=period,
            creator_id=creator_id,
            paid_views=views_by_creator[creator_id],
            amount_cents=amount,
        )

    period.ad_revenue_cents = ad_cents
    period.top_up_cents = top_up
    period.creator_pool_cents = pool
    period.paid_views = sum(views_by_creator.values())
    period.closed_at = timezone.now()
    period.save()
    return period


def balance_cents(user):
    earned = Earning.objects.filter(creator=user).aggregate(t=Sum("amount_cents"))["t"] or 0
    paid = (
        Payout.objects.filter(creator=user)
        .exclude(status="failed")
        .aggregate(t=Sum("amount_cents"))["t"]
        or 0
    )
    return earned - paid


class PayoutError(Exception):
    pass


@transaction.atomic
def request_payout(user):
    """Withdraw the full available balance to the creator's PayShap ShapID.

    The bank call is stubbed: in production this goes to a PayShap-enabled
    sponsor bank or a payments provider (e.g. Stitch, Ozow, Peach) and the
    status is updated from their webhook.
    """
    # Lock the user row so two taps on "withdraw" can't double-pay.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    profile = user.profile
    if not profile.can_earn:
        raise PayoutError("Verify your ID, age and PayShap details first.")
    amount = balance_cents(user)
    if amount < conf("MIN_PAYOUT_CENTS"):
        raise PayoutError(
            f"Minimum withdrawal is R{conf('MIN_PAYOUT_CENTS') / 100:.2f}."
        )
    payout = Payout.objects.create(
        creator=user, amount_cents=amount, shap_id=profile.payout_shap_id
    )
    payout.reference = f"SHAYA{payout.pk:08d}"
    payout.save(update_fields=["reference"])
    return payout


def estimate_for(user, month=None):
    """Live 'this month so far' numbers for the creator dashboard."""
    today = timezone.localdate()
    month = (month or today).replace(day=1)
    start, end = month_bounds(month)
    eligible = monetised_video_ids(end)
    paid_views = View.objects.filter(
        video__creator=user,
        qualified=True,
        created_at__gte=start,
        created_at__lt=end,
        video_id__in=eligible,
    ).count()
    last = PayoutPeriod.objects.filter(closed_at__isnull=False).first()
    rate = last.rate_per_1000_cents if last else 0
    return {
        "month": month,
        "paid_views": paid_views,
        "rate_per_1000_cents": rate,
        "estimate_cents": paid_views * rate // 1000,
        "last_period": last,
    }


def previous_month(today=None):
    today = today or timezone.localdate()
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


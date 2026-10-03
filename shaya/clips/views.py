import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import media, monetisation
from .forms import CommentForm, ProfileForm, ReportForm, SignUpForm, VideoUploadForm
from .models import AdCampaign, AdImpression, Comment, Follow, Like, Video

FEED_SIZE = 30


def _visible_videos():
    return (
        Video.objects.filter(is_removed=False)
        .select_related("creator", "creator__profile")
        .annotate(
            n_likes=Count("likes", distinct=True),
            n_comments=Count("comments", distinct=True),
            n_views=Count("views", filter=Q(views__qualified=True), distinct=True),
        )
    )


def _score(video, now):
    """Simple 'For You' ranking: engagement, decayed by age.

    Deliberately transparent so it can be published and audited. A real
    recommender (watch-time model, collaborative filtering) replaces this
    once there's enough data.
    """
    age_hours = (now - video.created_at).total_seconds() / 3600
    engagement = 1 + video.n_likes * 2 + video.n_comments * 3 + video.n_views * 0.1
    return engagement / (age_hours + 2) ** 1.5


def _with_ads(videos, every_n):
    """Interleave one sponsored clip after every `every_n` organic clips."""
    items = []
    used = []
    for i, v in enumerate(videos, start=1):
        items.append({"video": v, "ad": None})
        if i % every_n == 0:
            campaign = monetisation.pick_campaign(exclude_ids=used)
            if campaign:
                used.append(campaign.pk)
                ad_video = _visible_videos().filter(pk=campaign.video_id).first()
                if ad_video:
                    items.append({"video": ad_video, "ad": campaign})
    return items


def feed(request):
    tab = request.GET.get("tab", "foryou")
    lang = request.GET.get("lang", "")
    q = request.GET.get("q", "").strip()
    qs = _visible_videos()
    if lang:
        qs = qs.filter(language=lang)
    if q:
        qs = qs.filter(Q(caption__icontains=q) | Q(creator__username__icontains=q))

    if tab == "following":
        if not request.user.is_authenticated:
            return redirect("login")
        qs = qs.filter(creator__followers__follower=request.user)
        videos = list(qs.order_by("-created_at")[:FEED_SIZE])
    else:
        now = timezone.now()
        recent = list(qs.filter(created_at__gte=now - timedelta(days=30))[:300])
        if len(recent) < FEED_SIZE:
            seen = {v.pk for v in recent}
            recent += [v for v in qs[:FEED_SIZE] if v.pk not in seen]
        videos = sorted(recent, key=lambda v: _score(v, now), reverse=True)[:FEED_SIZE]

    liked = set()
    if request.user.is_authenticated:
        liked = set(
            Like.objects.filter(user=request.user, video__in=videos).values_list(
                "video_id", flat=True
            )
        )
    return render(
        request,
        "clips/feed.html",
        {
            "items": _with_ads(videos, settings.SHAYA["AD_EVERY_N_CLIPS"]),
            "liked": liked,
            "tab": tab,
            "lang": lang,
            "q": q,
            "languages": Video._meta.get_field("language").choices,
        },
    )


def video_detail(request, pk):
    video = get_object_or_404(_visible_videos(), pk=pk)
    liked = (
        request.user.is_authenticated
        and Like.objects.filter(user=request.user, video=video).exists()
    )
    return render(
        request,
        "clips/video_detail.html",
        {
            "video": video,
            "liked": liked,
            "comments": video.comments.select_related("user")[:200],
            "comment_form": CommentForm(),
            "report_form": ReportForm(),
        },
    )


@require_POST
def view_beacon(request, pk):
    video = get_object_or_404(Video, pk=pk, is_removed=False)
    try:
        watch_ms = int(json.loads(request.body or b"{}").get("watch_ms", 0))
    except (ValueError, TypeError, AttributeError):
        return HttpResponseBadRequest("bad watch_ms")
    viewer = request.user if request.user.is_authenticated else None
    view = monetisation.record_view(
        video, viewer, monetisation.viewer_key_for(request), watch_ms
    )
    return JsonResponse({"qualified": view.qualified})


@require_POST
def ad_impression(request, pk):
    campaign = get_object_or_404(AdCampaign, pk=pk, active=True)
    key = monetisation.viewer_key_for(request)
    # Advertisers pay at most once per viewer per hour: protects them from
    # someone scrolling back and forth over the same ad.
    recent = AdImpression.objects.filter(
        campaign=campaign,
        viewer_key=key,
        created_at__gte=timezone.now() - timedelta(hours=1),
    ).exists()
    if not recent:
        monetisation.charge_impression(campaign, key)
    return JsonResponse({"charged": not recent})


@login_required
@require_POST
def toggle_like(request, pk):
    video = get_object_or_404(Video, pk=pk, is_removed=False)
    like, created = Like.objects.get_or_create(user=request.user, video=video)
    if not created:
        like.delete()
    return JsonResponse({"liked": created, "count": video.likes.count()})


@login_required
@require_POST
def toggle_follow(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return HttpResponseBadRequest("You can't follow yourself")
    follow, created = Follow.objects.get_or_create(follower=request.user, following=target)
    if not created:
        follow.delete()
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"following": created, "count": target.followers.count()})
    return redirect("profile", username=username)


@login_required
@require_POST
def add_comment(request, pk):
    video = get_object_or_404(Video, pk=pk, is_removed=False)
    form = CommentForm(request.POST)
    if form.is_valid():
        Comment.objects.create(user=request.user, video=video, text=form.cleaned_data["text"])
    return redirect("video_detail", pk=pk)


@require_POST
def report_video(request, pk):
    video = get_object_or_404(Video, pk=pk)
    form = ReportForm(request.POST)
    if form.is_valid():
        report = form.save(commit=False)
        report.video = video
        report.reporter = request.user if request.user.is_authenticated else None
        report.save()
        messages.success(request, "Thanks. Our moderation team will review this clip.")
    return redirect("video_detail", pk=pk)


@login_required
def upload(request):
    if request.method == "POST":
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.creator = request.user
            video.save()
            duration = media.probe_duration(video.file.path)
            if duration and duration > settings.SHAYA["MAX_DURATION_SECONDS"]:
                video.file.delete(save=False)
                video.delete()
                form.add_error("file", "Clips can be at most 3 minutes long.")
            else:
                media.make_data_saver_copy(video)
                messages.success(request, "Your clip is live. Share it on WhatsApp!")
                return redirect("video_detail", pk=video.pk)
    else:
        profile = request.user.profile
        form = VideoUploadForm(initial={"language": profile.language, "province": profile.province})
    return render(request, "clips/upload.html", {"form": form})


def profile(request, username):
    owner = get_object_or_404(User.objects.select_related("profile"), username=username)
    videos = _visible_videos().filter(creator=owner).order_by("-created_at")
    is_following = (
        request.user.is_authenticated
        and Follow.objects.filter(follower=request.user, following=owner).exists()
    )
    return render(
        request,
        "clips/profile.html",
        {
            "owner": owner,
            "videos": videos,
            "is_following": is_following,
            "n_followers": owner.followers.count(),
            "n_following": owner.following.count(),
        },
    )


@login_required
def dashboard(request):
    user = request.user
    threshold = settings.SHAYA["MONETISE_THRESHOLD_VIEWS"]
    videos = _visible_videos().filter(creator=user).order_by("-created_at")
    rows = [
        {
            "video": v,
            "progress": min(100, v.n_views * 100 // threshold),
            "monetised": v.n_views >= threshold,
        }
        for v in videos
    ]
    return render(
        request,
        "clips/dashboard.html",
        {
            "rows": rows,
            "threshold": threshold,
            "estimate": monetisation.estimate_for(user),
            "balance_cents": monetisation.balance_cents(user),
            "earnings": user.earnings.select_related("period")[:12],
            "payouts": user.payouts.order_by("-created_at")[:12],
            "min_payout_cents": settings.SHAYA["MIN_PAYOUT_CENTS"],
            "creator_share_pct": settings.SHAYA["CREATOR_SHARE_BPS"] / 100,
        },
    )


@login_required
@require_POST
def withdraw(request):
    try:
        payout = monetisation.request_payout(request.user)
    except monetisation.PayoutError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"R{payout.amount_cents / 100:.2f} is on its way to {payout.shap_id} "
            f"(ref {payout.reference}).",
        )
    return redirect("dashboard")


@login_required
def edit_profile(request):
    form = ProfileForm(request.POST or None, instance=request.user.profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saved.")
        return redirect("profile", username=request.user.username)
    return render(request, "clips/edit_profile.html", {"form": form})


@require_POST
def toggle_data_saver(request):
    if request.user.is_authenticated:
        p = request.user.profile
        p.data_saver = not p.data_saver
        p.save(update_fields=["data_saver"])
    else:
        request.session["data_saver"] = not request.session.get("data_saver", True)
    return redirect(request.POST.get("next") or "feed")


def signup(request):
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.profile.date_of_birth = form.cleaned_data["date_of_birth"]
        user.profile.save()
        login(request, user)
        messages.success(request, "Welcome to Shaya! Post your first clip.")
        return redirect("upload")
    return render(request, "registration/signup.html", {"form": form})


def about(request):
    return render(
        request,
        "clips/about.html",
        {
            "threshold": settings.SHAYA["MONETISE_THRESHOLD_VIEWS"],
            "creator_share_pct": settings.SHAYA["CREATOR_SHARE_BPS"] / 100,
            "min_payout_rands": settings.SHAYA["MIN_PAYOUT_CENTS"] / 100,
        },
    )


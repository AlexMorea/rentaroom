import logging
import os

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import BadHeaderError, EmailMessage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from billing import pricing
from placements.models import Placement

from ..forms import ContactMessageForm
from ..models import Contact, Profile, Review, Room, RoomStat
from .auth_views import _client_ip

CONTACT_RECIPIENT_EMAIL = "hello@rooms4you.co.za"

# Contact form throttle, mirroring the signup one in auth_views: counts
# every POST from a network, so a script can't flood the inbox.
CONTACT_MAX_ATTEMPTS = 5
CONTACT_WINDOW_SECONDS = 3600

logger = logging.getLogger(__name__)


def home(request):
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()

    # redirect search to room list
    if request.GET.get("go") == "1":
        params = []

        if q:
            params.append(f"q={q}")

        if location:
            params.append(f"location={location}")

        if room_type:
            params.append(f"type={room_type}")

        querystring = "&".join(params)

        return redirect(
            f"/rooms/?{querystring}"
            if querystring
            else "/rooms/"
        )

    context = {
        "room_count": Room.objects.count(),
        "contact_count": Contact.objects.count(),
        "review_count": Review.objects.count(),
        "landlord_count": Profile.objects.filter(
            role="landlord"
        ).count(),

        "values": {
            "q": q,
            "location": location,
            "type": room_type,
        },

        "selected": {
            "any": room_type == "",
            "Single Room": room_type == "Single Room",
            "Shared Room": room_type == "Shared Room",
            "Bachelor": room_type == "Bachelor",
            "Ensuite": room_type == "Ensuite",
            "Student Accommodation": room_type == "Student Accommodation",
            "Backroom": room_type == "Backroom",
            "Cottage": room_type == "Cottage",
            "Apartment": room_type == "Apartment",
        },
    }

    return render(
        request,
        "listings/home.html",
        context
    )


def about(request):
    return render(request, "listings/about.html")


def support(request):
    return render(request, "listings/support.html")


def terms(request):
    return render(
        request,
        "listings/terms.html"
    )


def privacy(request):
    return render(
        request,
        "listings/privacy.html"
    )


def safety(request):
    return render(
        request,
        "listings/safety.html"
    )


def services(request):
    context = {
        "rooms_available": Room.objects.filter(is_available=True).count(),
        "total_rooms": Room.objects.count(),
        "contacts_made": RoomStat.objects.filter(stat_type__startswith="contact").count(),
        # Real, dual-confirmed move-ins (the old "success" RoomStat type
        # was never written anywhere, so this always showed 0).
        "move_ins": Placement.objects.filter(
            status__in=[Placement.STATUS_MOVED_IN, Placement.STATUS_SUCCESS_FEE_DUE, Placement.STATUS_PAID]
        ).count(),
        "pro_from": pricing.PRO_BANDS[0].monthly_price,
        "boost_from": pricing.BOOST_OPTIONS[0].price,
    }
    return render(request, "listings/services.html", context)


def contact(request):
    if request.method == "POST" and (request.POST.get("website") or "").strip():
        # Honeypot tripped. Answer exactly as a real send would, so the
        # bot has no signal that it was caught - nothing is emailed.
        logger.info("Contact form honeypot triggered from IP %s", _client_ip(request))
        messages.success(request, "Thanks for getting in touch. We'll reply as soon as we can.")
        return redirect("contact")

    if request.method == "POST":
        contact_key = f"contact_attempts:{_client_ip(request)}"
        attempts = cache.get(contact_key, 0)

        if attempts >= CONTACT_MAX_ATTEMPTS:
            messages.error(
                request,
                "Too many messages from this network. Please try again later, or email "
                f"{CONTACT_RECIPIENT_EMAIL} directly.",
            )
            return render(request, "listings/contact.html", {"form": ContactMessageForm(request.POST)})

        cache.set(contact_key, attempts + 1, timeout=CONTACT_WINDOW_SECONDS)
        form = ContactMessageForm(request.POST)

        if form.is_valid():
            name = form.cleaned_data["name"]
            email = form.cleaned_data["email"]
            reason = dict(ContactMessageForm.REASON_CHOICES)[form.cleaned_data["reason"]]
            message = form.cleaned_data["message"]

            try:
                EmailMessage(
                    subject=f"[Rooms4You Contact] {reason} from {name}",
                    body=f"From: {name} <{email}>\nReason: {reason}\n\n{message}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[CONTACT_RECIPIENT_EMAIL],
                    reply_to=[email],
                ).send()
                messages.success(
                    request,
                    "Thanks for getting in touch. We'll reply as soon as we can.",
                )
                return redirect("contact")
            except BadHeaderError:
                messages.error(request, "Part of your message couldn't be sent. Please check it and try again.")
            except Exception:
                logger.exception("Failed to send contact form email")
                messages.error(
                    request,
                    "We couldn't send your message just now. Please email "
                    f"{CONTACT_RECIPIENT_EMAIL} directly instead.",
                )
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = ContactMessageForm()

    return render(request, "listings/contact.html", {"form": form})


def offline_page(request):
    """Served by the service worker when a navigation request fails
    while offline and nothing cached matches it."""
    return render(request, "listings/offline.html")


def service_worker_view(request):
    """
    Serves the service worker at the site ROOT (e.g. rooms4you.co.za/service-worker.js)
    rather than from /static/js/. A service worker's default scope is
    limited to the directory it's served from - if this lived at
    /static/js/service-worker.js it would only be able to control
    /static/js/*, not the actual site pages. Serving it via a root-level
    view sidesteps needing a Service-Worker-Allowed header on WhiteNoise.
    """
    sw_path = os.path.join(settings.BASE_DIR, "static", "js", "service-worker.js")
    with open(sw_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HttpResponse(content, content_type="application/javascript")


def robots_txt(request):
    """Tells search engine crawlers what they can index and points them
    at the sitemap. Served dynamically (not a static file) so the
    sitemap URL is always correct without needing to hardcode it twice."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /dashboard/",
        "Disallow: /landlord/",
        "Disallow: /profile/",
        "Disallow: /inbox/",
        "Disallow: /rooms/*/edit/",
        "Disallow: /rooms/*/images/",
        "Disallow: /rooms/new/",
        "",
        f"Sitemap: https://www.rooms4you.co.za{reverse('sitemap')}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def assetlinks_json(request):
    """
    Digital Asset Links file Android's Trusted Web Activity uses to
    verify the Play Store app is allowed to open rooms4you.co.za links
    without the browser chrome/URL bar. Package name and cert
    fingerprints come from env vars (settings.TWA_PACKAGE_NAME /
    TWA_SHA256_FINGERPRINTS) instead of being hardcoded here, because
    they don't exist until someone actually generates the Android
    signing keystore (see mobile/android/README.md) - until then this
    correctly serves an empty array rather than 500ing or lying about a
    package that isn't published yet.
    """
    if not (settings.TWA_PACKAGE_NAME and settings.TWA_SHA256_FINGERPRINTS):
        return JsonResponse([], safe=False)

    return JsonResponse([
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": settings.TWA_PACKAGE_NAME,
                "sha256_cert_fingerprints": settings.TWA_SHA256_FINGERPRINTS,
            },
        }
    ], safe=False)



def pricing_refunds(request):
    """Public Pricing & Refunds page - prices come from billing.pricing,
    the same source checkout charges from, so they can't drift."""
    from accounts import founding
    from billing import pricing

    return render(request, "listings/pricing_refunds.html", {
        "bands": [
            {
                "band": band,
                "monthly": pricing.pro_price(band, pricing.CYCLE_MONTHLY),
                "annual": pricing.pro_price(band, pricing.CYCLE_ANNUAL),
                "founding_monthly": pricing.pro_price(band, pricing.CYCLE_MONTHLY, pricing.FOUNDING_DISCOUNT_PERCENT),
            }
            for band in pricing.PRO_BANDS
        ],
        "boost_options": pricing.BOOST_OPTIONS,
        "free_boosts_per_month": pricing.PRO_FREE_BOOSTS_PER_MONTH,
        "founding_discount": pricing.FOUNDING_DISCOUNT_PERCENT,
        "founding_grace_days": pricing.FOUNDING_LOCK_GRACE_DAYS,
        "founding_discount_months": pricing.FOUNDING_DISCOUNT_MONTHS,
        "founding_discount_until": founding.discount_until(),
        "annual_months_charged": pricing.ANNUAL_MONTHS_CHARGED,
    })

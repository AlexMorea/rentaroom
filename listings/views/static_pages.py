import logging
import os

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from ..models import Contact, Profile, Review, Room, RoomStat

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
        "success_matches": RoomStat.objects.filter(stat_type="success").count(),
    }
    return render(request, "listings/services.html", context)


def contact(request):
    return render(request, "listings/contact.html")


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


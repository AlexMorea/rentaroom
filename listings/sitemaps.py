from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Room


class RoomSitemap(Sitemap):
    """Every publicly available room listing - the pages most worth
    Google actually crawling and indexing."""

    changefreq = "daily"
    priority = 0.8
    protocol = "https"

    def items(self):
        return Room.objects.filter(is_available=True).only(
            "id", "created_at"
        ).order_by("id")

    def lastmod(self, obj):
        return obj.created_at

    def location(self, obj):
        # Just the path - Django's sitemap view prepends protocol+domain
        # itself (via the current request's host when django.contrib.sites
        # isn't installed). Prepending it here too would double it up.
        return reverse("room_detail", args=[obj.id])


class StaticViewSitemap(Sitemap):
    """Fixed pages that don't change often but are still worth Google
    knowing about."""

    changefreq = "weekly"
    priority = 0.5
    protocol = "https"

    def items(self):
        return [
            "home",
            "room_list",
            "about",
            "services",
            "contact",
            "safety",
            "terms",
            "privacy",
        ]

    def location(self, obj):
        # Django's Sitemap.location is typed for the common case where
        # items() yields model instances; this sitemap's items() yields
        # URL names (str) instead, which is an equally valid use of the
        # (untyped-at-runtime) Sitemap contract.
        return reverse(obj)  # pyright: ignore[reportArgumentType]

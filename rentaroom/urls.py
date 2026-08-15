from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from listings import views as listings_views
from listings.sitemaps import RoomSitemap, StaticViewSitemap

sitemaps = {
    "rooms": RoomSitemap,
    "static": StaticViewSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("service-worker.js", listings_views.service_worker_view, name="service_worker"),
    path("robots.txt", listings_views.robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("listings.urls")),
    path("accounts/", include("accounts.urls")),
    path("services/", include("services.urls")),
    path("trust/", include("trust.urls")),
    path("placements/", include("placements.urls")),
    path("stays/", include("stays.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

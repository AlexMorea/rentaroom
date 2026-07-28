from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from listings import views as listings_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("service-worker.js", listings_views.service_worker_view, name="service_worker"),
    path("", include("listings.urls")),
    path("accounts/", include("accounts.urls")),
    path("services/", include("services.urls")),
    path("trust/", include("trust.urls")),
    path("placements/", include("placements.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

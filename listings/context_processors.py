from django.conf import settings


def google_maps_key(request):
    return {
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY
    }


def seo_settings(request):
    return {
        "GOOGLE_SITE_VERIFICATION": settings.GOOGLE_SITE_VERIFICATION,
        "GA_MEASUREMENT_ID": settings.GA_MEASUREMENT_ID,
    }
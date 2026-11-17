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


def vapid_public_key(request):
    # Safe to expose - it's the whole point of a *public* key. The
    # matching private key never leaves settings/env vars.
    return {"VAPID_PUBLIC_KEY": settings.VAPID_PUBLIC_KEY}


def google_oauth_client_id(request):
    # Safe to expose - an OAuth client ID identifies the app to Google,
    # it isn't a secret (there is no client secret in this ID-token flow).
    return {"GOOGLE_OAUTH_CLIENT_ID": settings.GOOGLE_OAUTH_CLIENT_ID}

def company_details(request):
    """Legal/company disclosures used by the footer and legal pages."""
    return {
        "COMPANY": {
            "legal_name": settings.COMPANY_LEGAL_NAME,
            "trading_name": settings.COMPANY_TRADING_NAME,
            "reg_number": settings.COMPANY_REG_NUMBER,
            "vat_number": settings.COMPANY_VAT_NUMBER,
            "address": settings.COMPANY_ADDRESS,
            "phone": settings.COMPANY_PHONE,
            "directors": settings.COMPANY_DIRECTORS,
            "email": settings.COMPANY_EMAIL,
            "support_email": settings.COMPANY_SUPPORT_EMAIL,
            "billing_email": settings.COMPANY_BILLING_EMAIL,
            "privacy_email": settings.COMPANY_PRIVACY_EMAIL,
            "support_hours": settings.COMPANY_SUPPORT_HOURS,
            "website": settings.COMPANY_WEBSITE,
            "legal_last_updated": settings.LEGAL_LAST_UPDATED,
        }
    }

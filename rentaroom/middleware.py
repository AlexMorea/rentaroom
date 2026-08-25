"""
SEO and domain canonicalization middleware for Rooms4You.
Ensures all traffic is redirected to the canonical www domain.
"""
from django.http import HttpResponsePermanentRedirect
from django.conf import settings


class WWWRedirectMiddleware:
    """
    Redirect all non-www traffic to www version of the domain.
    
    This establishes a single canonical URL structure for SEO:
    - http://rooms4you.co.za → https://www.rooms4you.co.za
    - https://rooms4you.co.za → https://www.rooms4you.co.za
    - http://www.rooms4you.co.za → https://www.rooms4you.co.za
    
    Django's sitemap, robots.txt, and canonical tags all reference
    https://www.rooms4you.co.za/ as the single source of truth.
    
    This middleware is skipped in development (DEBUG=True) to avoid
    issues with localhost testing.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical_domain = "www.rooms4you.co.za"
    
    def __call__(self, request):
        # Skip redirect in development
        if settings.DEBUG:
            return self.get_response(request)
        
        host = request.get_host().lower()
        
        # If request is already to www version, continue normally
        if host == self.canonical_domain or host == self.canonical_domain + ":443":
            return self.get_response(request)
        
        # Don't redirect non-production domains (localhost, 127.0.0.1, *.onrender.com in non-www form,
        # testserver is Django's default test-client host)
        if host in ["127.0.0.1", "localhost", "testserver"] or "onrender.com" in host:
            return self.get_response(request)
        
        # Redirect to www version with HTTPS
        new_url = f"https://{self.canonical_domain}{request.get_full_path()}"
        return HttpResponsePermanentRedirect(new_url)

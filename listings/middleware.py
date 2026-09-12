class DisableCacheMiddleware:
    """
    Forces no-store on every response by default - the safe choice for
    authenticated/dashboard pages, which are per-user and often carry a
    session-bound CSRF token.

    That default previously applied to public, logged-out pages too
    (room list, room detail, home, etc.), which meant every anonymous
    visitor and every Google crawl re-fetched the full page even though
    listings/views/room_views.py already server-side caches those exact
    responses for up to 60s. Browsers/CDNs couldn't reuse that work.

    Anonymous GET/HEAD responses that don't set a cookie (i.e. nothing
    session- or CSRF-specific is being established on this response) are
    safe to let the browser cache briefly instead - same 60s TTL as the
    server-side cache they mirror, so a stale listing can't linger
    longer than the source of truth already allows.

    "private" here, not "public" - a real report from a live deploy
    showed why: "public" lets any SHARED cache along the way (a mobile
    carrier's data-saving proxy, a CDN edge) hold a copy and serve it to
    other visitors too, not just the browser that made the request. One
    of those grabbed a page in the few-second window around a deploy and
    kept serving that stale snapshot well past 60s to everyone behind
    it - on one visitor's phone the page looked half-updated (CSS is a
    separate, correctly-fresh request; the HTML itself was the stale
    part) while it was already correct for everyone else. "private"
    still lets that one visitor's own browser cache the page - it only
    stops it being shared.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        cacheable = (
            request.method in ("GET", "HEAD")
            and not request.user.is_authenticated
            and "Set-Cookie" not in response
        )

        if cacheable:
            response["Cache-Control"] = "private, max-age=60"
        else:
            response["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response
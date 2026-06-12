from django import template

register = template.Library()


@register.filter
def profile(user):
    """Return user's profile or None if unavailable."""
    try:
        return getattr(user, "profile", None)
    except Exception:
        return None

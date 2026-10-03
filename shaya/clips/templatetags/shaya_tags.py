from django import template

register = template.Library()


@register.filter
def rands(cents):
    """Format integer cents as South African Rand, e.g. 123456 -> R1 234.56."""
    try:
        cents = int(cents)
    except (TypeError, ValueError):
        return ""
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}R{whole:,}.{part:02d}".replace(",", " ")

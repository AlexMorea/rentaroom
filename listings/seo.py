import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe


def ld_json(data):
    """Serialize a dict to JSON safe for embedding in a
    <script type="application/ld+json"> tag.

    Room titles/descriptions are landlord-supplied text, so this can't
    just be json.dumps + mark_safe: a description containing
    "</script><script>..." would close the tag early and execute as
    real script. Escaping <, >, and & to unicode sequences (the same
    trick Django's own json_script filter uses) keeps the JSON valid
    while making that impossible.
    """
    encoded = json.dumps(data, cls=DjangoJSONEncoder)
    encoded = (
        encoded
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return mark_safe(encoded)

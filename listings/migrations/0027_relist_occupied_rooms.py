from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def relist_occupied_rooms(apps, schema_editor):
    """
    "Mark Occupied" used to switch rooms off (is_available=False), which
    removed them from search entirely. Occupied rooms are meant to stay
    listed as full so tenants can join the waitlist, so put back the ones
    that were hidden that way.

    The stale-listing job also hides rooms with available_units=0, but
    only once a room has gone 30+ days without confirmation, while "Mark
    Occupied" stamps last_confirmed_at with the time of the click. Rooms
    of suspended accounts (inactive owners) stay hidden.
    """
    Room = apps.get_model("listings", "Room")
    cutoff = timezone.now() - timedelta(days=30)
    Room.objects.filter(
        is_available=False,
        available_units__lte=0,
        last_confirmed_at__gt=cutoff,
        owner__is_active=True,
    ).update(is_available=True)


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0026_blocked_user"),
    ]

    operations = [
        migrations.RunPython(relist_occupied_rooms, migrations.RunPython.noop),
    ]

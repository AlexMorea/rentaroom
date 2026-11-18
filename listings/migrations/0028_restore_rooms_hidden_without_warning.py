from django.db import migrations
from django.db.models import F


def restore_rooms(apps, schema_editor):
    """
    The stale-listing job's first ever run hid every room unconfirmed for
    30+ days in one sweep, without sending the "please confirm" nudge
    first, and zeroed their available_units. Put those rooms back with
    their vacancy restored. They keep their old last_confirmed_at, so the
    next run sends the landlord a proper nudge, and the job now only
    hides a room after that nudge has been ignored for a week.

    Rooms hidden that way were never nudged (last_nudge_sent_at is null)
    and have no free units. Rooms of suspended accounts stay hidden.
    """
    Room = apps.get_model("listings", "Room")
    Room.objects.filter(
        is_available=False,
        available_units__lte=0,
        last_nudge_sent_at__isnull=True,
        owner__is_active=True,
    ).update(is_available=True, available_units=F("total_units"))


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0027_relist_occupied_rooms"),
    ]

    operations = [
        migrations.RunPython(restore_rooms, migrations.RunPython.noop),
    ]

from django.db import migrations


def relist_rooms(apps, schema_editor):
    """
    The stale-listing job sent its first "please confirm" nudges around
    19 Nov and, a week later, hid every room whose landlord hadn't
    clicked confirm - most of the rooms on the site. Hiding is now off by
    default (LISTING_AUTO_HIDE_ENABLED), so put those rooms back.

    A room the job paused still claims a vacancy (it keeps
    available_units) and was nudged first. Rooms of suspended accounts
    stay hidden: suspension deactivates the login and suspends the
    membership. last_confirmed_at is left alone, so tenants still see
    honestly how long ago the landlord last confirmed.
    """
    Room = apps.get_model("listings", "Room")
    Room.objects.filter(
        is_available=False,
        available_units__gt=0,
        last_nudge_sent_at__isnull=False,
        owner__is_active=True,
    ).exclude(owner__membership__status="suspended").update(is_available=True)


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0028_restore_rooms_hidden_without_warning"),
        ("accounts", "0007_move_to_free_and_pro"),
    ]

    operations = [
        migrations.RunPython(relist_rooms, migrations.RunPython.noop),
    ]

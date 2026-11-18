from django.db import migrations
from django.db.models import Exists, OuterRef


def remove_tap_only_enquiries(apps, schema_editor):
    """
    Until now, tapping Call/WhatsApp/Email on a listing (or a landlord
    messaging a tenant first) created an "Interested" placement, which
    later triggered "Still interested?" emails and inflated landlords'
    enquiry numbers. Interest now means the tenant actually messaged the
    landlord, so drop the placements that never got that far: still at
    Interested, no viewing or move-in date set, and the tenant has never
    sent the landlord a message about that room. The taps themselves are
    kept in RoomStat, so landlords' contact counts don't change.
    """
    Placement = apps.get_model("placements", "Placement")
    Message = apps.get_model("listings", "Message")
    tenant_wrote = Message.objects.filter(room_id=OuterRef("room_id"), sender_id=OuterRef("tenant_id"))
    Placement.objects.filter(
        status="interested",
        viewing_date__isnull=True,
        move_in_date__isnull=True,
    ).exclude(Exists(tenant_wrote)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("placements", "0008_discontinue_success_fee"),
        ("listings", "0028_restore_rooms_hidden_without_warning"),
    ]

    operations = [
        migrations.RunPython(remove_tap_only_enquiries, migrations.RunPython.noop),
    ]

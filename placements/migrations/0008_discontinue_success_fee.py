"""
The room success fee is discontinued. Any invoice still pending is
waived, and its placement goes back to "Moved In" - which is still
recorded, counted and shown as a successful placement.
"""
from django.db import migrations

REASON = "Success fee discontinued"


def forwards(apps, schema_editor):
    PlacementInvoice = apps.get_model("placements", "PlacementInvoice")
    Placement = apps.get_model("placements", "Placement")

    pending = PlacementInvoice.objects.filter(status="pending")
    placement_ids = list(pending.values_list("placement_id", flat=True))
    pending.update(status="waived", waiver_reason=REASON)
    Placement.objects.filter(id__in=placement_ids, status="success_fee_due").update(status="moved_in")


class Migration(migrations.Migration):
    dependencies = [
        ("placements", "0007_founding_landlord"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

# Adds landlord-controlled image ordering
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0016_add_avail_score_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="roomimage",
            name="order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="roomimage",
            options={"ordering": ["order", "created_at"]},
        ),
    ]

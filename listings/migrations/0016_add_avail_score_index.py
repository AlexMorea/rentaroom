from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0015_add_score"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="room",
            index=models.Index(fields=["is_available", "score", "created_at"], name="room_avail_score_created_idx"),
        ),
    ]

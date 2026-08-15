from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0018_roomstat_composite_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='deposit_amount',
            field=models.PositiveIntegerField(blank=True, help_text='Leave blank if no deposit is required.', null=True),
        ),
    ]
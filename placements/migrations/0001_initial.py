import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("listings", "0016_add_avail_score_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="Placement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[
                    ("interested", "Interested"),
                    ("viewing_scheduled", "Viewing Scheduled"),
                    ("viewing_completed", "Viewing Completed"),
                    ("approved", "Approved"),
                    ("moved_in", "Moved In"),
                    ("success_fee_due", "Success Fee Due"),
                    ("paid", "Paid"),
                    ("verification_required", "Verification Required"),
                    ("cancelled", "Cancelled"),
                ], default="interested", max_length=30)),
                ("viewing_date", models.DateTimeField(blank=True, null=True)),
                ("move_in_date", models.DateField(blank=True, null=True)),
                ("tenant_confirmed_move_in", models.BooleanField(blank=True, null=True)),
                ("landlord_confirmed_move_in", models.BooleanField(blank=True, null=True)),
                ("tenant_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("landlord_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("move_in_check_sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("landlord", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="placements_as_landlord", to=settings.AUTH_USER_MODEL)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="placements", to="listings.room")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="placements_as_tenant", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PlacementStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(blank=True, max_length=30)),
                ("to_status", models.CharField(max_length=30)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, help_text="Who/what triggered this change. Null = system (signal/management command).")),
                ("placement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_history", to="placements.placement")),
            ],
            options={
                "ordering": ["created_at"],
                "verbose_name_plural": "Placement status history",
            },
        ),
        migrations.CreateModel(
            name="PlacementInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=8)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                    ("waived", "Waived"),
                ], default="pending", max_length=20)),
                ("payment_reference", models.CharField(blank=True, max_length=50)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("marked_paid_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoices_marked_paid", to=settings.AUTH_USER_MODEL, help_text="Staff member who confirmed payment.")),
                ("placement", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="invoice", to="placements.placement")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="placement",
            constraint=models.UniqueConstraint(fields=("tenant", "room"), name="uniq_placement_tenant_room"),
        ),
        migrations.AddIndex(
            model_name="placement",
            index=models.Index(fields=["status"], name="placements_status_idx"),
        ),
        migrations.AddIndex(
            model_name="placement",
            index=models.Index(fields=["landlord", "status"], name="placements_landlord_status_idx"),
        ),
        migrations.AddIndex(
            model_name="placement",
            index=models.Index(fields=["tenant", "status"], name="placements_tenant_status_idx"),
        ),
        migrations.AddIndex(
            model_name="placement",
            index=models.Index(fields=["move_in_date"], name="placements_move_in_date_idx"),
        ),
    ]

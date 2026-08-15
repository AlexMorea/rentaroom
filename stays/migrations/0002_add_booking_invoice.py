import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stays', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BookingInvoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('waived', 'Waived')], default='pending', max_length=20)),
                ('payment_reference', models.CharField(blank=True, max_length=50)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('booking', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='invoice', to='stays.booking')),
                ('marked_paid_by', models.ForeignKey(blank=True, help_text='Staff member who confirmed payment.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stay_invoices_marked_paid', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
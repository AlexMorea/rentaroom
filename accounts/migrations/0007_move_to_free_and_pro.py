"""
Moves every landlord onto the Free / Pro model.

- Founding Landlords -> Pro, free until the programme date (their trial
  end, never shortened), with the 50% founding price lock.
- Everyone else -> Free (unlimited listings), no trial.
- Landlords who were locked out only because a 30-day trial ran out are
  switched back on. A genuine Trust & Safety suspension (login disabled
  as well) is left exactly as it is.

No landlord had paid when this shipped, so there's no paid period to
carry over.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    from accounts import founding

    Membership = apps.get_model("accounts", "Membership")
    free_until = founding.free_until()

    for membership in Membership.objects.select_related("user"):
        trust_suspended = not membership.user.is_active

        if membership.is_founding:
            membership.tier = "pro"
            membership.is_trial = True
            if membership.trial_end is None or membership.trial_end < free_until:
                membership.trial_end = free_until
            membership.founding_discount_percent = 50
        else:
            membership.tier = "free"
            membership.is_trial = False

        membership.payment_requested = False
        membership.requested_tier = None

        if not trust_suspended:
            membership.is_active = True
            membership.status = "active"

        membership.save()


def backwards(apps, schema_editor):
    Membership = apps.get_model("accounts", "Membership")
    Membership.objects.filter(tier="pro").update(tier="gold")
    Membership.objects.filter(tier="free").update(tier="starter")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_free_pro_billing_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

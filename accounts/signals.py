from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver

from listings.models import Profile
from accounts.utils import get_or_create_membership


@receiver(post_save, sender=User)
def create_membership(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        profile = instance.profile
    except Profile.DoesNotExist:
        return

    if profile.role == "landlord":
        get_or_create_membership(instance)
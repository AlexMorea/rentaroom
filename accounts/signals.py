from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Membership

@receiver(post_save, sender=User)
def create_membership(sender, instance, created, **kwargs):
    if created:
        Membership.objects.create(user=instance)
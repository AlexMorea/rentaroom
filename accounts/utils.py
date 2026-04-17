import uuid
from django.utils import timezone
from datetime import timedelta
from .models import Membership

def get_or_create_membership(user):
    membership, created = Membership.objects.get_or_create(
        user=user,
        defaults={
            "tier": "starter",
            "is_active": True,
            "is_trial": True,
            "trial_end": timezone.now() + timedelta(days=30)
        }
    )

    if not membership.membership_id:
        membership.membership_id = f"R4Y-{uuid.uuid4().hex[:6].upper()}"
        membership.save()

    return membership

def require_active_membership(user):
    membership = get_or_create_membership(user)

    if membership.is_trial and membership.trial_end and timezone.now() > membership.trial_end:
        return False

    return True
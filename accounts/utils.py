from django.utils import timezone
from datetime import timedelta
from .models import Membership
from .helpers import generate_membership_id


def get_or_create_membership(user):

    if user.profile.role != "landlord":
        return None

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
        membership.membership_id = generate_membership_id()
        membership.save()

    return membership


def require_active_membership(user):
    membership = get_or_create_membership(user)

    if membership.is_trial and membership.trial_end and timezone.now() > membership.trial_end:
        return False

    return True
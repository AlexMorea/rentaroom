from datetime import timedelta

from django.utils import timezone

from .helpers import generate_membership_id
from .models import Membership


def get_or_create_membership(user):

    if user.profile.role != "landlord":
        return None

    membership, _ = Membership.objects.get_or_create(
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

    # get_or_create_membership returns None for non-landlords - both
    # current call sites are already gated behind @user_passes_test
    # (is_landlord), so this is defensive rather than reachable today.
    # Membership trial expiry isn't a concept that applies to a
    # non-landlord, so don't block them.
    if membership is None:
        return True

    return not (
        membership.is_trial
        and membership.trial_end
        and timezone.now() > membership.trial_end
    )
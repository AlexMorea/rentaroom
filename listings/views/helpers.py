import logging

from accounts.helpers import generate_membership_id
from accounts.models import Membership

logger = logging.getLogger(__name__)


def get_display_name(user):
    return (user.first_name or "").strip() or (user.email or "").strip() or "there"


def get_or_create_membership(user):
    membership, _ = Membership.objects.get_or_create(user=user)

    # Ensure membership ID always exists
    if not membership.membership_id:
        membership.membership_id = generate_membership_id()
        membership.save(update_fields=["membership_id"])

    return membership


def is_landlord(user):
    return hasattr(user, "profile") and user.profile.role == "landlord"


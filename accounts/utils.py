from .helpers import generate_membership_id
from .models import Membership


def get_or_create_membership(user):

    if user.profile.role != "landlord":
        return None

    membership, _ = Membership.objects.get_or_create(user=user)

    if not membership.membership_id:
        membership.membership_id = generate_membership_id()
        membership.save()

    return membership


def require_active_membership(user):
    """True unless Trust & Safety has suspended this landlord. Plans and
    payments never block managing listings - Free is unlimited."""
    membership = get_or_create_membership(user)

    if membership is None:
        return False

    return membership.can_create_listing()

"""
Trust & safety account moderation. One function, shared by admin actions
in listings.admin (ProfileAdmin) and trust.admin (FraudReportAdmin), so
"suspend this suspicious account" always does the full job - deactivate
the login, hide every live listing, and pause billing - instead of staff
having to remember three separate manual steps across two admin pages.
"""
import logging

from django.contrib.auth.models import User

from accounts.models import Membership

logger = logging.getLogger(__name__)


def suspend_account(user: User) -> dict:
    # Local imports: listings imports accounts.models (Membership) at
    # module load time, so importing listings back at accounts' own
    # module level would be a circular import - safe here since this
    # only runs after all apps are loaded.
    from listings.models import Room
    from listings.utils import clear_room_list_cache

    was_active = user.is_active
    if was_active:
        user.is_active = False
        user.save(update_fields=["is_active"])

    hidden_rooms = Room.objects.filter(owner=user, is_available=True).update(is_available=False)

    membership_suspended = False
    membership = Membership.objects.filter(user=user).first()
    if membership and membership.status != "suspended":
        membership.status = "suspended"
        membership.is_active = False
        membership.save(update_fields=["status", "is_active"])
        membership_suspended = True

    if hidden_rooms:
        clear_room_list_cache(user.id)

    logger.info(
        "Suspended account %s: deactivated=%s hidden_rooms=%d membership_suspended=%s",
        user.username, was_active, hidden_rooms, membership_suspended,
    )

    return {
        "deactivated": was_active,
        "hidden_rooms": hidden_rooms,
        "membership_suspended": membership_suspended,
    }

import importlib

from django.core.management import call_command
from django.db import DatabaseError

from .models import RoomStat

# Load Celery dynamically so static analyzers do not require the optional
# worker dependency to be installed in the current environment.
shared_task = importlib.import_module("celery").shared_task


@shared_task
def create_room_view_stat_task(room_id, user_id=None):
    """Create a RoomStat record for a room view. Runs inside Celery worker."""
    try:
        RoomStat.objects.create(
            room_id=room_id,
            user_id=user_id,
            stat_type="view",
        )
    except DatabaseError:
        # Be resilient — do not raise inside periodic/background tasks
        pass

@shared_task
def compute_scores_task(force=False):
    """Run the management command to compute and persist room scores.
    Set force=True to apply updates.
    """
    args = []
    if force:
        args.append("--force")
    call_command("compute_scores", *args)


@shared_task
def flag_stale_listings_task(force=False):
    """Nudge landlords about unconfirmed listings, auto-hide the ones
    that never respond. Set force=True to actually send/apply."""
    args = []
    if force:
        args.append("--force")
    call_command("flag_stale_listings", *args)


@shared_task
def send_landlord_digest_task(force=False):
    """Weekly per-landlord performance + tips email/push. Set force=True
    to actually send."""
    args = []
    if force:
        args.append("--force")
    call_command("send_landlord_digest", *args)

from celery import shared_task
from django.core.management import call_command
from .models import RoomStat


@shared_task
def create_room_view_stat_task(room_id, user_id=None):
    """Create a RoomStat record for a room view. Runs inside Celery worker."""
    try:
        RoomStat.objects.create(
            room_id=room_id,
            user_id=user_id,
            stat_type="view",
        )
    except Exception:
        # Be resilient — do not raise inside periodic/background tasks
        return None

@shared_task
def compute_scores_task(force=False):
    """Run the management command to compute and persist room scores.
    Set force=True to apply updates.
    """
    args = []
    if force:
        args.append("--force")
    call_command("compute_scores", *args)

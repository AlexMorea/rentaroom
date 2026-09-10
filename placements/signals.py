from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from listings.models import Contact, Room

from .models import Placement, PlacementStatusHistory, Waitlist


@receiver(post_save, sender=Contact)
def create_placement_from_contact(sender, instance: Contact, created, **kwargs):
    """
    Every existing entry point that expresses tenant interest - the
    phone/WhatsApp/email buttons (track_contact) and the in-platform
    message form (send_message) - already creates a Contact record.
    Hooking here means Placements appear automatically everywhere a
    tenant "begins the rental process", with zero changes to those
    existing views.
    """
    if not created:
        return

    room = instance.room
    tenant = instance.user

    # A landlord messaging/"contacting" their own room isn't a placement.
    if tenant.id == room.owner_id:
        return

    Placement.objects.get_or_create(
        tenant=tenant,
        room=room,
        defaults={"landlord": room.owner},
    )


@receiver(pre_save, sender=Placement)
def record_status_change(sender, instance: Placement, **kwargs):
    """
    Writes an audit-trail row whenever status actually changes. Using
    pre_save (comparing against the DB row) rather than trusting a view
    to call this explicitly means the history can't be forgotten or
    bypassed, including for admin overrides and management-command-driven
    changes (move-in confirmation flow).
    """
    if instance._state.adding:
        # Brand new placement - log its initial status once it has a pk.
        return

    try:
        previous = Placement.objects.get(pk=instance.pk)
    except Placement.DoesNotExist:
        return

    if previous.status == instance.status:
        return

    # Stash on the instance; written in post_save once we have a pk
    # (harmless for existing rows, required for correctness on new ones).
    instance._status_changed_from = previous.status


@receiver(post_save, sender=Placement)
def write_status_history(sender, instance: Placement, created, **kwargs):
    if created:
        PlacementStatusHistory.objects.create(
            placement=instance,
            from_status="",
            to_status=instance.status,
        )
        return

    from_status = getattr(instance, "_status_changed_from", None)
    if from_status is not None:
        PlacementStatusHistory.objects.create(
            placement=instance,
            from_status=from_status,
            to_status=instance.status,
        )
        # Clear so a subsequent unrelated .save() in the same request
        # doesn't re-log a stale transition.
        instance._status_changed_from = None


def _has_vacancy(room: Room) -> bool:
    return room.is_available and room.available_units > 0


@receiver(pre_save, sender=Room)
def stash_previous_room_vacancy(sender, instance: Room, **kwargs):
    """
    Stashes whether the room had a vacancy *before* this save, so
    notify_waitlist_when_room_becomes_available can tell a genuine
    "was full, now isn't" transition apart from an unrelated save (e.g.
    editing the description) that happens to leave availability alone.
    """
    if instance._state.adding:
        instance._had_vacancy = None
        return

    try:
        previous = Room.objects.get(pk=instance.pk)
    except Room.DoesNotExist:
        instance._had_vacancy = None
        return

    instance._had_vacancy = _has_vacancy(previous)


@receiver(post_save, sender=Room)
def notify_waitlist_when_room_becomes_available(sender, instance: Room, created, **kwargs):
    if created:
        return

    had_vacancy = getattr(instance, "_had_vacancy", None)
    if had_vacancy is False and _has_vacancy(instance):
        Waitlist.notify_all_for_room(instance)

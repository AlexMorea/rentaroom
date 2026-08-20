from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from listings.models import Contact

from .models import Placement, PlacementStatusHistory


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

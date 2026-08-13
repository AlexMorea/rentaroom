import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from datetime import timedelta
from django.db.models import Count, Q, F, IntegerField, ExpressionWrapper, Avg
from django.http import HttpResponseForbidden, HttpResponse, Http404
from django.urls import reverse
from django.contrib import messages
from ..models import Message
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import strip_tags
from ..models import Room, Review, Contact, RoomStat, RoomImage, Profile, Favorite
import logging

logger = logging.getLogger(__name__)


@login_required
def send_message(request, room_id):
    """
    Kept for backward compatibility with any old links/bookmarks pointing
    here - immediately hands off to the real two-way conversation view.
    New code should link straight to conversation_thread.
    """
    room = get_object_or_404(Room, id=room_id)

    if request.user.id == room.owner_id:
        messages.error(request, "Open a specific conversation to reply to a tenant.")
        return redirect("inbox")

    if request.method == "POST":
        return conversation_thread(request, room_id=room.id, other_user_id=room.owner_id)

    return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)


@login_required
def conversation_thread(request, room_id, other_user_id):
    """
    A single message thread between two specific users about one room.
    Works identically for both roles:
      - Tenant's view: other_user_id is always the room's owner.
      - Landlord's view: other_user_id is whichever tenant they're
        replying to (a room can have many separate tenant conversations).

    This - not a new model - is what actually fixes "messaging should
    work between landlord and tenant": the old send_message() only
    allowed tenant-to-landlord and explicitly forbade the room owner
    from using it, and inbox() was landlord-only, so a landlord had no
    way to reply and a tenant had no way to see a reply even if one
    existed.
    """
    room = get_object_or_404(Room, id=room_id)
    other_user = get_object_or_404(User, id=other_user_id)

    is_owner = request.user.id == room.owner_id

    if is_owner:
        if other_user.id == room.owner_id:
            return HttpResponseForbidden("Invalid conversation.")
    else:
        # A tenant can only have a thread with this room's owner - not
        # with some arbitrary other user.
        if other_user.id != room.owner_id:
            return HttpResponseForbidden("Invalid conversation.")
        if request.user.id == room.owner_id:
            return HttpResponseForbidden()

    if request.method == "POST":
        body = strip_tags((request.POST.get("body") or "").strip())

        if not body:
            messages.error(request, "Message cannot be empty.")
        elif len(body) > 2000:
            messages.error(request, "Message too long.")
        else:
            recent_count = Message.objects.filter(
                sender=request.user,
                created_at__gte=timezone.now() - timedelta(minutes=1)
            ).count()

            if recent_count >= 5:
                messages.error(request, "Too many messages sent. Please wait a minute.")
            else:
                Message.objects.create(
                    room=room,
                    sender=request.user,
                    recipient=other_user,
                    body=body,
                )
                # Contact is always attributed to whichever party isn't
                # the room owner (i.e. the tenant side of the conversation).
                Contact.objects.get_or_create(
                    room=room,
                    user=request.user if not is_owner else other_user,
                )

        return redirect("conversation_thread", room_id=room.id, other_user_id=other_user.id)

    thread_qs = (
        Message.objects.filter(room=room)
        .filter(
            (Q(sender=request.user) & Q(recipient=other_user))
            | (Q(sender=other_user) & Q(recipient=request.user))
        )
        .select_related("sender", "recipient")
        .order_by("created_at")
    )

    # Mark anything sent TO the current user as read now that they've
    # opened the thread.
    Message.objects.filter(
        room=room, sender=other_user, recipient=request.user, is_read=False
    ).update(is_read=True)

    return render(request, "listings/conversation_thread.html", {
        "room": room,
        "other_user": other_user,
        "is_owner": is_owner,
        "thread": thread_qs,
    })


@login_required
def inbox(request):
    """
    Works for both tenants and landlords now (previously landlord-only).
    Groups every message the user has sent or received into one row per
    (room, other person), showing the latest message and an unread count -
    a normal "conversation list" rather than a flat message log.
    """
    msgs = (
        Message.objects.filter(Q(sender=request.user) | Q(recipient=request.user))
        .select_related("room", "sender", "recipient")
        .order_by("-created_at")
    )

    conversations = {}
    for m in msgs:
        other = m.recipient if m.sender_id == request.user.id else m.sender
        key = (m.room_id, other.id)

        if key not in conversations:
            conversations[key] = {
                "room": m.room,
                "other_user": other,
                "last_message": m,
                "unread_count": 0,
            }

        if m.recipient_id == request.user.id and not m.is_read:
            conversations[key]["unread_count"] += 1

    conversation_list = sorted(
        conversations.values(),
        key=lambda c: c["last_message"].created_at,
        reverse=True,
    )

    return render(request, "listings/inbox.html", {
        "conversations": conversation_list,
    })


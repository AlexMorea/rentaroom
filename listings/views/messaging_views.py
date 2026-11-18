import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from accounts.push import notify_user
from placements.models import Placement
from trust.models import FraudReport
from trust.scam_detection import auto_flag_if_scammy
from utils.email import send_template_email

from ..models import BlockedUser, Contact, Message, Room

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


MAX_MESSAGE_LENGTH = 2000
MESSAGES_PER_MINUTE = 5


def _thread_parties(request, room_id, other_user_id):
    """Returns (room, other_user, is_owner) or raises/returns a 403.
    A tenant can only talk to the room's owner; the owner can talk to
    any tenant about their room, but not to themselves."""
    room = get_object_or_404(Room, id=room_id)
    other_user = get_object_or_404(User, id=other_user_id)
    is_owner = request.user.id == room.owner_id

    if is_owner and other_user.id == room.owner_id:
        return None
    if not is_owner and other_user.id != room.owner_id:
        return None
    return room, other_user, is_owner


def _thread_messages(room, me, other):
    return (
        Message.objects.filter(room=room)
        .filter((Q(sender=me) & Q(recipient=other)) | (Q(sender=other) & Q(recipient=me)))
        .select_related("sender")
        .order_by("created_at")
    )


def _message_json(msg, me):
    local = timezone.localtime(msg.created_at)
    return {
        "id": msg.id,
        "mine": msg.sender_id == me.id,
        "body": msg.body,
        "time": local.strftime("%H:%M"),
        "day": local.strftime("%Y-%m-%d"),
        "day_label": _day_label(local),
        "read": msg.is_read,
    }


def _day_label(local_dt):
    today = timezone.localdate()
    day = local_dt.date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return local_dt.strftime("%-d %B %Y") if day.year != today.year else local_dt.strftime("%-d %B")


def _wants_json(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _notify_new_message(msg, room, sender, recipient, already_unread):
    """Push every message; email only the first unread one in a
    conversation, so a burst of messages means one email, not ten."""
    sender_name = sender.first_name or sender.username
    thread_url = reverse("conversation_thread", args=[room.id, sender.id])

    notify_user(
        recipient,
        title=f"New message from {sender_name}",
        body=msg.body[:120],
        url=thread_url,
    )

    if already_unread or not recipient.email:
        return
    try:
        send_template_email(
            subject=f"{sender_name} sent you a message about \"{room.title}\"",
            to_email=recipient.email,
            template="emails/new_message.html",
            context={
                "recipient": recipient,
                "sender_name": sender_name,
                "room": room,
                "excerpt": msg.body[:300],
                "thread_url": f"https://www.rooms4you.co.za{thread_url}",
            },
        )
    except Exception:  # noqa: BLE001 - email trouble must never block a message
        logger.exception("Failed to email new-message notice for message %s", msg.pk)


@login_required
def conversation_thread(request, room_id, other_user_id):
    """
    A single message thread between two specific users about one room.
    Works for both roles: a tenant always talks to the room's owner; the
    owner can reply to any tenant who wrote about that room.

    Sending works as a normal form post (no JavaScript needed) or as a
    fetch() call that returns JSON, so the page can add the message
    without reloading.
    """
    parties = _thread_parties(request, room_id, other_user_id)
    if parties is None:
        return HttpResponseForbidden("Invalid conversation.")
    room, other_user, is_owner = parties

    blocked = BlockedUser.between(request.user, other_user)
    i_blocked = BlockedUser.objects.filter(blocker=request.user, blocked=other_user).exists()

    if request.method == "POST":
        body = strip_tags((request.POST.get("body") or "").strip())
        error = None

        if blocked:
            error = "You can't send messages in this conversation."
        elif not body:
            error = "Please type a message first."
        elif len(body) > MAX_MESSAGE_LENGTH:
            error = f"Messages can be up to {MAX_MESSAGE_LENGTH} characters."
        elif Message.objects.filter(
            sender=request.user, created_at__gte=timezone.now() - timedelta(minutes=1)
        ).count() >= MESSAGES_PER_MINUTE:
            error = "You're sending messages very quickly. Please wait a minute and try again."

        if error:
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": error}, status=400)
            messages.error(request, error)
            return redirect("conversation_thread", room_id=room.id, other_user_id=other_user.id)

        already_unread = Message.objects.filter(
            room=room, sender=request.user, recipient=other_user, is_read=False
        ).exists()
        msg = Message.objects.create(room=room, sender=request.user, recipient=other_user, body=body)

        # Contact is always attributed to the tenant side of the conversation.
        Contact.objects.get_or_create(room=room, user=request.user if not is_owner else other_user)
        if not is_owner:
            # A tenant writing to the landlord is what counts as interest.
            Placement.record_interest(request.user, room)
        _notify_new_message(msg, room, request.user, other_user, already_unread)
        auto_flag_if_scammy(
            text=body,
            source_key=f"message:{request.user.id}:{room.id}",
            category=FraudReport.CATEGORY_DEPOSIT_SCAM,
            room=room,
            reported_user=request.user,
        )

        if _wants_json(request):
            return JsonResponse({"ok": True, "message": _message_json(msg, request.user)})
        return redirect("conversation_thread", room_id=room.id, other_user_id=other_user.id)

    thread_qs = list(_thread_messages(room, request.user, other_user))

    # Opening the thread marks everything sent to me as read.
    Message.objects.filter(
        room=room, sender=other_user, recipient=request.user, is_read=False
    ).update(is_read=True)

    last_mine = next((m for m in reversed(thread_qs) if m.sender_id == request.user.id), None)

    return render(request, "listings/conversation_thread.html", {
        "room": room,
        "other_user": other_user,
        "is_owner": is_owner,
        "thread": thread_qs,
        "last_mine_id": last_mine.id if last_mine else None,
        "last_mine_read": bool(last_mine and last_mine.is_read),
        "blocked": blocked,
        "i_blocked": i_blocked,
        "max_length": MAX_MESSAGE_LENGTH,
        "today_iso": timezone.localdate().isoformat(),
        "quick_replies": (
            ["Yes, the room is still available.", "When would you like to come and view it?",
             "Sorry, the room has been taken."]
            if is_owner else
            ["Is the room still available?", "When can I come and view it?",
             "What does the rent include?"]
        ),
    })


@login_required
def conversation_poll(request, room_id, other_user_id):
    """New messages since ?after=<id>, plus whether my last message has
    been seen. Marks the other person's new messages as read, since the
    thread is open on screen."""
    parties = _thread_parties(request, room_id, other_user_id)
    if parties is None:
        return HttpResponseForbidden()
    room, other_user, _ = parties

    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        after = 0

    new = list(_thread_messages(room, request.user, other_user).filter(id__gt=after))
    Message.objects.filter(
        room=room, sender=other_user, recipient=request.user, is_read=False
    ).update(is_read=True)

    last_mine = (
        Message.objects.filter(room=room, sender=request.user, recipient=other_user)
        .order_by("-created_at").first()
    )
    return JsonResponse({
        "messages": [_message_json(m, request.user) for m in new],
        "last_mine_id": last_mine.id if last_mine else None,
        "last_mine_read": bool(last_mine and last_mine.is_read),
    })


@login_required
def unread_summary(request):
    """Unread count and the newest unread message, for the badges and
    the 'new message' pop-up shown on every page."""
    unread = Message.objects.filter(recipient=request.user, is_read=False)
    latest = unread.select_related("sender", "room").order_by("-created_at").first()
    data = {"count": unread.count(), "latest": None}
    if latest:
        data["latest"] = {
            "id": latest.id,
            "from": latest.sender.first_name or latest.sender.username,
            "room": latest.room.title,
            "url": reverse("conversation_thread", args=[latest.room_id, latest.sender_id]),
        }
    return JsonResponse(data)


@login_required
@require_POST
def toggle_block(request, room_id, other_user_id):
    parties = _thread_parties(request, room_id, other_user_id)
    if parties is None:
        return HttpResponseForbidden()
    room, other_user, _ = parties
    name = other_user.first_name or "this person"

    existing = BlockedUser.objects.filter(blocker=request.user, blocked=other_user)
    if existing.exists():
        existing.delete()
        messages.success(request, f"You've unblocked {name}. You can message each other again.")
    else:
        BlockedUser.objects.create(blocker=request.user, blocked=other_user)
        messages.success(request, f"You've blocked {name}. They can no longer send you messages.")
    return redirect("conversation_thread", room_id=room.id, other_user_id=other_user.id)


@login_required
@require_POST
def report_conversation(request, room_id, other_user_id):
    """Files a FraudReport with the last messages attached, so Trust &
    Safety see exactly what was said."""
    parties = _thread_parties(request, room_id, other_user_id)
    if parties is None:
        return HttpResponseForbidden()
    room, other_user, _ = parties

    recent = list(_thread_messages(room, request.user, other_user))[-15:]
    transcript = "\n".join(
        f"[{timezone.localtime(m.created_at):%d %b %H:%M}] "
        f"{'Reporter' if m.sender_id == request.user.id else 'Reported user'}: {m.body}"
        for m in recent
    )
    reason = (request.POST.get("reason") or "").strip()[:500]
    report = FraudReport.objects.create(
        reporter=request.user,
        room=room,
        reported_user=other_user,
        category=FraudReport.CATEGORY_SCAM if request.POST.get("kind") == "scam" else FraudReport.CATEGORY_ABUSE,
        detail=(f"Reported from a conversation about \"{room.title}\".\n"
                f"Reporter's note: {reason or '(none)'}\n\nRecent messages:\n{transcript}"),
    )
    messages.success(
        request,
        f"Thank you. We've received your report (reference {report.reference_code}) and our Trust & Safety "
        "team will look into it. You can also block this person below.",
    )
    return redirect("conversation_thread", room_id=room.id, other_user_id=other_user.id)


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


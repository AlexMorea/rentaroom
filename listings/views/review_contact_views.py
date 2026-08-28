import logging
import re
from smtplib import SMTPException
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from utils.email import send_template_email

from ..models import Contact, Message, Review, Room, RoomStat

try:
    from twilio.base.exceptions import TwilioException
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.voice_response import VoiceResponse
except ImportError:
    # twilio is in requirements.txt, but guarded the same defensive way
    # as this project's existing Celery imports (see tasks.py) - a
    # missing/failed twilio install shouldn't crash the whole app, it
    # should just make call_landlord() fall back to in-app messaging.
    TwilioClient = None
    TwilioException = RuntimeError
    VoiceResponse = None
logger = logging.getLogger(__name__)


@login_required
@require_POST
def add_review(request, room_id):
    room = get_object_or_404(Room, id=room_id)

    # ROLE CHECK (SYSTEM MESSAGE INSTEAD OF RAW ERROR)
    if hasattr(request.user, "profile") and request.user.profile.role != "tenant":
        messages.warning(request, "Only tenants are allowed to review rooms.")
        return redirect("room_detail", pk=room.id)

    # Only tenants who've actually reached out about this room can review
    # it - otherwise anyone could review any room sight unseen, and since
    # reviews now feed the ranking score, that'd be an easy way to game it.
    if not Contact.objects.filter(room=room, user=request.user).exists():
        messages.warning(
            request,
            "You can review a room after contacting the landlord about it."
        )
        return redirect("room_detail", pk=room.id)

    rating = request.POST.get("rating")
    comment = request.POST.get("comment", "")

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        rating = None

    if rating is None or not (1 <= rating <= 5):
        messages.error(request, "Please provide a rating between 1 and 5 stars.")
        return redirect("room_detail", pk=room.id)

    Review.objects.update_or_create(
        room=room,
        user=request.user,
        defaults={
            "rating": rating,
            "comment": comment
        }
    )

    messages.success(request, "Your review has been submitted successfully.")
    return redirect("room_detail", pk=room.id)


@login_required
@require_POST
def report_room(request, pk):
    room = get_object_or_404(Room, pk=pk)

    reason = (request.POST.get("reason") or "").strip()
    detail = (request.POST.get("detail") or "").strip()

    # reason required
    if not reason:
        messages.error(
            request,
            "Please select a reason to report this listing."
        )
        return redirect("room_detail", pk=room.id)

    # if "other", require detail
    if reason.lower() == "other" and not detail:
        messages.error(
            request,
            "Please provide more detail for 'Other'."
        )
        return redirect("room_detail", pk=room.id)

    logger.info(
        f"ROOM REPORT | room={room.id} | "
        f"user={request.user.id if request.user.is_authenticated else 'anonymous'} | "
        f"reason={reason} | detail={detail}"
    )

    messages.success(
        request,
        "Thanks! Your report was received ✅ We’ll review this listing."
    )

    return redirect("room_detail", pk=room.id)


@login_required
def track_contact(request, room_id, method):
    """
    Direct external contact - Call opens the phone dialer, WhatsApp opens
    a chat with the landlord's real WhatsApp, Email opens a mailto:. This
    is the straightforward version: real contact info, no masking yet.

    In-app chat (conversation_thread) stays available as its own separate
    option alongside these - not a replacement for them. Masked calling
    via Twilio (call_landlord/voice_bridge_twiml, further down this file)
    is built and ready but not linked from the UI yet - switch "Call
    Landlord" over to call_landlord once real Twilio credentials are
    configured.
    """
    if method not in ["phone", "whatsapp", "email"]:
        return HttpResponseForbidden("Invalid contact method.")

    room = get_object_or_404(Room, id=room_id, is_available=True)

    if request.user.id == room.owner_id:
        messages.error(request, "You can't contact yourself about your own listing.")
        return redirect("room_detail", pk=room.id)

    cache_key = f"contact:{request.user.id}:{room.id}:{method}"

    if cache.get(cache_key):
        return redirect("room_detail", pk=room.id)

    cache.set(cache_key, True, 300)

    RoomStat.objects.get_or_create(
        room=room,
        user=request.user,
        stat_type=f"contact_{method}",
    )
    Contact.objects.get_or_create(room=room, user=request.user)

    phone_raw = (room.contact_phone or "").strip()
    whatsapp_raw = (room.contact_whatsapp or "").strip() or phone_raw
    phone_digits = re.sub(r"\D", "", whatsapp_raw)
    landlord_email = (room.contact_email or room.owner.email or "").strip()

    if method == "phone":
        tel = phone_raw.replace(" ", "")
        if not tel:
            return redirect("room_detail", pk=room.id)

        return render(
            request,
            "listings/external_link.html",
            {
                "title": "Calling landlord…",
                "link": f"tel:{tel}",
                "button_text": "Tap to Call",
                "fallback_text": "If your phone didn't open the dialer automatically, tap the button below.",
            },
        )

    if method == "whatsapp":
        if not phone_digits or len(phone_digits) < 9:
            return redirect("room_detail", pk=room.id)

        whatsapp_url = f"https://wa.me/{phone_digits}"

        return render(
            request,
            "listings/external_link.html",
            {
                "title": "Opening WhatsApp…",
                "link": whatsapp_url,
                "button_text": "Open WhatsApp",
                "fallback_text": "If WhatsApp didn't open automatically, tap the button below.",
            },
        )

    if method == "email":
        if not landlord_email:
            return redirect("room_detail", pk=room.id)

        subject = quote(f"Rooms4You enquiry: {room.title}")
        body = quote(f"Hi, I'm interested in your room listing ({room.title}) in {room.location}.")
        mailto = f"mailto:{landlord_email}?subject={subject}&body={body}"

        try:
            send_template_email(
                subject="New inquiry on your listing",
                to_email=room.owner.email,
                template="emails/new_inquiry.html",
                context={
                    "room": room,
                    "user": request.user,
                    "year": 2026
                }
            )
        except (SMTPException, OSError):
            logger.warning("Failed to send new-inquiry notification email for room %s", room.id)

        return render(
            request,
            "listings/external_link.html",
            {
                "title": "Opening email…",
                "link": mailto,
                "button_text": "Open Email",
                "fallback_text": "If your email app didn't open automatically, tap the button below.",
            },
        )

    return redirect("room_detail", pk=room.id)


def call_landlord(request, room_id):
    """
    The real "Call Landlord" behavior - attempts a masked two-leg call
    via Twilio (like Uber/Airbnb: Twilio calls the tenant, and once they
    answer, bridges them to the landlord - neither side ever sees the
    other's real number, only Twilio's).

    Falls back to an in-app message (same as before) if Twilio Voice
    isn't configured yet (settings.TWILIO_VOICE_ENABLED is computed from
    whether real credentials are present - see rentaroom/settings.py) or
    if the tenant hasn't got a phone number on file to call. This means
    the feature is safe to ship now and will start actually placing
    calls the moment Twilio credentials are added, with no code change.
    """
    room = get_object_or_404(Room, id=room_id, is_available=True)

    if request.user.id == room.owner_id:
        messages.error(request, "You can't contact yourself about your own listing.")
        return redirect("room_detail", pk=room.id)

    cache_key = f"contact:{request.user.id}:{room.id}:phone"
    if cache.get(cache_key):
        return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)
    cache.set(cache_key, True, 300)

    RoomStat.objects.get_or_create(room=room, user=request.user, stat_type="contact_phone")
    Contact.objects.get_or_create(room=room, user=request.user)

    tenant_phone = ""
    if hasattr(request.user, "profile"):
        tenant_phone = (request.user.profile.phone_number or "").strip()
    landlord_phone = (room.contact_phone or "").strip()

    can_place_call = (
        settings.TWILIO_VOICE_ENABLED
        and TwilioClient is not None
        and tenant_phone
        and landlord_phone
    )

    if not can_place_call:
        Message.objects.create(
            room=room,
            sender=request.user,
            recipient=room.owner,
            body="Hi, I'd like to arrange a call about this room. What's a good time to reach you?",
        )
        if not settings.TWILIO_VOICE_ENABLED:
            messages.info(
                request,
                "In-app calling isn't switched on yet - we've sent the landlord "
                "a message asking them to arrange a call with you.",
            )
        elif not tenant_phone:
            messages.info(
                request,
                "Add a phone number to your profile so we can connect your call "
                "directly next time. For now, we've messaged the landlord for you.",
            )
        else:
            messages.info(
                request,
                "This landlord hasn't added a phone number yet - we've sent "
                "them a message instead.",
            )
        return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)

    try:
        # can_place_call above already required TwilioClient is not None -
        # this just makes that provable rather than tracked only through
        # the boolean variable.
        assert TwilioClient is not None
        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        callback_url = request.build_absolute_uri(
            reverse("voice_bridge_twiml", args=[room.id])
        )
        client.calls.create(
            to=tenant_phone,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=callback_url,
        )
        messages.success(
            request,
            "Calling you now - stay on the line and we'll connect you to the landlord.",
        )
    except (TwilioException, OSError, ValueError):
        logger.exception("Failed to place masked call for room %s", room.id)
        Message.objects.create(
            room=room,
            sender=request.user,
            recipient=room.owner,
            body="Hi, I tried to call about this room but the call didn't go through - could you reach out?",
        )
        messages.error(
            request,
            "We couldn't start the call right now. We've sent the landlord a message instead.",
        )

    return redirect("room_detail", pk=room.id)


@csrf_exempt
def voice_bridge_twiml(request, room_id):
    """
    Twilio requests this URL once the tenant answers the outbound call
    placed in call_landlord() above. Returns TwiML telling Twilio to
    dial the landlord's number and bridge the two calls - this is the
    step where masking actually happens: Twilio's number is what shows
    up as caller ID on the landlord's end, never the tenant's real one.

    Must stay unauthenticated and CSRF-exempt - Twilio's servers call
    this directly, not a logged-in browser session.
    """
    if VoiceResponse is None:
        # twilio isn't installed in this environment - Twilio's servers
        # shouldn't be calling this webhook if the feature isn't
        # configured, but fail safely rather than crashing if they do.
        return HttpResponse(status=503)

    room = get_object_or_404(Room, id=room_id)
    landlord_phone = (room.contact_phone or "").strip()

    response = VoiceResponse()
    if landlord_phone:
        response.say("Connecting you to the landlord now.")
        response.dial(landlord_phone, caller_id=settings.TWILIO_PHONE_NUMBER)
    else:
        response.say("Sorry, we could not connect this call. Please try messaging instead.")

    return HttpResponse(str(response), content_type="text/xml")


    return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)


@login_required
def mark_success(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    RoomStat.objects.get_or_create(room=room, user=request.user, stat_type="success")
    messages.success(request, "Thanks for confirming!")
    return redirect("room_detail", pk=room.id)


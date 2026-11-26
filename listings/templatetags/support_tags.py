"""
The WhatsApp support link, pre-filled with where it was tapped.

Support chats used to open blank, so there was no telling whether a chat
came from the app or from a poster, or whether someone tapped "help" on
a room page thinking it would reach the landlord. Every chat started
from the app now opens with a tag such as
"[Rooms4You app · Browse rooms]". Chats without one came from somewhere
else (a poster, the number typed in by hand).
"""
from urllib.parse import quote

from django import template
from django.conf import settings

register = template.Library()

# Friendly names for the pages people most often ask for help from.
# Anything not listed falls back to the page's address.
PAGE_LABELS = {
    "home": "Home page",
    "room_list": "Browse rooms",
    "room_detail": "Room page",
    "register": "Sign up",
    "login": "Log in",
    "verify_account": "Verification code",
    "verify_device": "Device code",
    "google_complete_profile": "Google sign-up",
    "password_reset": "Forgot password",
    "become_landlord": "Become a landlord",
    "create_room": "Post a room",
    "edit_room": "Edit room",
    "upload_room_images": "Add photos",
    "edit_room_images": "Manage photos",
    "dashboard": "Landlord dashboard",
    "landlord_rooms": "My rooms",
    "inbox": "Messages",
    "conversation_thread": "Chat",
    "profile": "Profile",
    "edit_profile": "Edit profile",
    "account_settings": "Settings",
    "support": "Help page",
    "contact": "Contact page",
}

MAX_TITLE_CHARS = 60


def support_source_label(request, room=None) -> str:
    match = getattr(request, "resolver_match", None)
    name = getattr(match, "url_name", "") or ""
    label = PAGE_LABELS.get(name) or getattr(request, "path", "") or "app"

    room_id = getattr(room, "pk", None)
    if room_id:
        if name == "room_detail":
            title = (getattr(room, "title", "") or "").strip()
            if len(title) > MAX_TITLE_CHARS:
                title = title[: MAX_TITLE_CHARS - 1].rstrip() + "…"
            label = f"Room #{room_id}: {title}" if title else f"Room #{room_id}"
        else:
            label = f"{label} · Room #{room_id}"
    return label


@register.simple_tag(takes_context=True)
def support_whatsapp_url(context):
    label = support_source_label(context.get("request"), context.get("room"))
    text = f"[Rooms4You app · {label}]\nHi, I need help with: "
    return f"https://wa.me/{settings.SUPPORT_WHATSAPP_NUMBER}?text={quote(text)}"

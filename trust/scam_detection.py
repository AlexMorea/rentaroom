"""
Lightweight, dependency-free heuristics for the rental-scam patterns this
platform is most exposed to: the classic "pay a deposit before you can
view" advance-fee scam, and requests to pay through untraceable channels
(gift cards, crypto, Western Union/MoneyGram) instead of a normal EFT.

Deliberately narrow. This is a South African rental platform where EFT
deposits (Room.deposit_amount) are a completely normal, expected part of
renting - the patterns below only match scam-specific phrasing, never
plain words like "deposit", "EFT" or "bank transfer" on their own, so a
legitimate landlord's listing or message is never touched by this.

A match doesn't block anything - it opens a FraudReport so Trust & Safety
sees it fast (the same post_save signal that already emails
SAFETY_TEAM_EMAIL for every report), while the listing/message stays
live. False positives cost staff a two-minute dismiss; a missed scam
costs a tenant real money, so the bar for flagging is deliberately lower
than the bar for blocking.
"""
import logging
import re

from django.core.cache import cache

logger = logging.getLogger(__name__)

# (label, pattern) - label is what staff see in the auto-generated report.
SCAM_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "gift card requested as payment",
        re.compile(r"\b(itunes|google\s*play|steam|amazon)\s+(gift\s*card|voucher)\b", re.I),
    ),
    (
        "gift card requested as payment",
        re.compile(r"\bgift\s*cards?\b.{0,40}\b(pay|payment|deposit|rent)\b", re.I),
    ),
    (
        "requests payment via Western Union/MoneyGram",
        re.compile(r"\b(western\s*union|moneygram|money\s*gram)\b", re.I),
    ),
    (
        "requests payment via crypto",
        re.compile(r"\b(bitcoin|btc|usdt|crypto\s*wallet|binance)\b.{0,40}\b(pay|payment|deposit|wallet\s*address)\b", re.I),
    ),
    (
        "requests payment via crypto",
        re.compile(r"\b(pay|payment|deposit)\b.{0,40}\b(bitcoin|btc|usdt|crypto)\b", re.I),
    ),
    (
        "asks for payment before a viewing",
        re.compile(r"\b(pay|send|transfer)\b.{0,40}\bdeposit\b.{0,40}\bbefore\b.{0,20}\b(view|viewing|inspect|inspection)\b", re.I),
    ),
    (
        "asks for payment before a viewing",
        re.compile(r"\bno\s+(need\s+to\s+)?view(ing)?\b.{0,40}\b(sign|pay|deposit)\b", re.I),
    ),
    (
        "landlord claims to be unreachable in person",
        re.compile(r"\b(currently\s+(out\s+of\s+the\s+country|abroad|overseas)|on\s+a\s+mission(ary)?\s+trip|cannot\s+meet\s+in\s+person)\b", re.I),
    ),
    (
        "offers to courier keys instead of a viewing",
        re.compile(r"\b(courier|post|mail)\b.{0,30}\bkeys?\b", re.I),
    ),
]

# Don't re-flag the exact same source (a room, or a sender+room pair)
# more than once a day - a chatty scammer repeating the same phrase
# shouldn't flood the trust queue with one report per message/edit.
AUTO_FLAG_COOLDOWN_SECONDS = 60 * 60 * 24


def find_scam_signals(text: str) -> list[str]:
    if not text:
        return []

    labels = []
    for label, pattern in SCAM_PATTERNS:
        if label not in labels and pattern.search(text):
            labels.append(label)
    return labels


def auto_flag_if_scammy(*, text, source_key, category, room=None, reported_user=None):
    """
    Scans `text` and, if it matches a known scam pattern, opens a
    FraudReport (unless one was already auto-opened for this exact
    `source_key` within the last 24h). Never raises - a bug here must
    never block a listing save or a message send.
    """
    try:
        signals = find_scam_signals(text)
        if not signals:
            return None

        cache_key = f"trust:autoflag:{source_key}"
        if cache.get(cache_key):
            return None
        cache.set(cache_key, True, timeout=AUTO_FLAG_COOLDOWN_SECONDS)

        from .models import FraudReport

        snippet = text.strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"

        detail = (
            "Auto-flagged by the scam-language scanner — matched: "
            f"{', '.join(signals)}.\n\nText: {snippet}"
        )

        report = FraudReport.objects.create(
            room=room,
            reported_user=reported_user,
            category=category,
            detail=detail,
        )
        logger.info("Auto-flagged FraudReport #%s for source %s", report.pk, source_key)
        return report
    except Exception:
        logger.exception("Scam auto-flag failed for source %s", source_key)
        return None

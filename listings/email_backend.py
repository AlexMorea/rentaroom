import json
import logging
import os
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class BrevoEmailBackend(BaseEmailBackend):
    """
    Django EmailBackend that sends emails via Brevo HTTP API.
    Safe for Render free tier (no SMTP).
    """

    API_URL = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        api_key = os.environ.get("BREVO_API_KEY", "").strip()
        if not api_key:
            logger.error("BREVO_API_KEY missing. No emails sent.")
            return 0

        sent_count = 0

        for m in email_messages:
            # --- Resolve sender ---
            raw_from = (m.from_email or os.environ.get("DEFAULT_FROM_EMAIL") or "").strip()
            name, sender_email = parseaddr(raw_from)  # extracts pure email

            # fallback: if DEFAULT_FROM_EMAIL had no brackets, parseaddr may put email in name
            if not sender_email and "@" in raw_from and "<" not in raw_from:
                sender_email = raw_from
                name = "Rooms4You"

            if not sender_email:
                logger.error("No valid sender email. DEFAULT_FROM_EMAIL=%r", raw_from)
                continue

            sender_name = (name or os.environ.get("BREVO_SENDER_NAME") or "Rooms4You").strip()

            # --- Recipients ---
            to_emails = [addr for addr in (m.to or []) if addr]
            if not to_emails:
                logger.error("No recipients found for message subject=%r", m.subject)
                continue

            to_list = [{"email": addr} for addr in to_emails]

            # --- Subject ---
            subject = (m.subject or "Rooms4You Notification").strip() or "Rooms4You Notification"

            # --- Extract HTML alternative (if exists) ---
            html_body = ""
            if getattr(m, "alternatives", None):
                for content, mimetype in m.alternatives:
                    if mimetype == "text/html" and content:
                        html_body = content.strip()
                        break

            # --- TEXT: Brevo requires non-empty textContent ---
            text_body = (m.body or "").strip()

            # If Django produced html-only, body may be empty -> give a safe fallback
            if not text_body:
                text_body = (
                    "Rooms4You\n\n"
                    "We received a request to reset your password.\n"
                    "If you requested this, use the reset link in this email.\n"
                    "If you did not request this, you can ignore this message.\n"
                )

            payload = {
                "sender": {"name": sender_name, "email": sender_email},
                "to": to_list,
                "subject": subject,
                "textContent": text_body,  # ✅ never empty
            }

            if html_body:
                payload["htmlContent"] = html_body

            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": api_key,
            }

            req = urllib.request.Request(
                self.API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                    if 200 <= resp.status < 300:
                        sent_count += 1
                        logger.info("Brevo OK (%s) -> %s | %s", resp.status, to_emails, body)
                    else:
                        logger.error("Brevo non-2xx (%s): %s", resp.status, body)

            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                logger.error("Brevo HTTPError %s: %s", e.code, err_body)
                if not self.fail_silently:
                    raise

            except Exception:
                logger.exception("Brevo send failed")
                if not self.fail_silently:
                    raise

        return sent_count

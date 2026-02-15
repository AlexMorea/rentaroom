import json
import os
import urllib.request
import urllib.error
import logging
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
            name, email = parseaddr(raw_from)  # <- IMPORTANT (extracts pure email)

            # fallback: if DEFAULT_FROM_EMAIL had no brackets, parseaddr may return email in name
            if not email and "@" in raw_from and "<" not in raw_from:
                email = raw_from
                name = "Rooms4You"

            if not email:
                logger.error("No valid sender email. DEFAULT_FROM_EMAIL=%r", raw_from)
                continue

            sender_name = (name or os.environ.get("BREVO_SENDER_NAME") or "Rooms4You").strip()

            # --- Recipients ---
            to_emails = [addr for addr in (m.to or []) if addr]
            if not to_emails:
                logger.error("No recipients found for message subject=%r", m.subject)
                continue

            to_list = [{"email": addr} for addr in to_emails]

            payload = {
                "sender": {"name": sender_name, "email": email},
                "to": to_list,
                "subject": m.subject or "Rooms4You Notification",
                "textContent": m.body or "",
            }

            # If html alternative exists, add it
            if getattr(m, "alternatives", None):
                for content, mimetype in m.alternatives:
                    if mimetype == "text/html":
                        payload["htmlContent"] = content
                        break

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
                # 🔥 This will show the REAL Brevo reason for 400/401/403
                err_body = e.read().decode("utf-8", errors="ignore")
                logger.error("Brevo HTTPError %s: %s", e.code, err_body)
                if not self.fail_silently:
                    raise

            except Exception as e:
                logger.exception("Brevo send failed: %s", e)
                if not self.fail_silently:
                    raise

        return sent_count

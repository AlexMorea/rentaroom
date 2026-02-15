import json
import os
import urllib.request
import urllib.error
import logging

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class BrevoEmailBackend(BaseEmailBackend):
    """
    Django EmailBackend that sends emails via Brevo HTTP API.
    Works on Render free tier (no SMTP needed).
    """

    API_URL = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        api_key = (os.environ.get("BREVO_API_KEY") or "").strip()
        if not api_key:
            logger.error("BREVO_API_KEY is missing. No emails sent.")
            return 0

        sandbox = (os.environ.get("BREVO_SANDBOX") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        default_from = (os.environ.get("DEFAULT_FROM_EMAIL") or "").strip()

        sent_count = 0

        for m in email_messages:
            try:
                from_email = (m.from_email or default_from or "").strip()
                if not from_email:
                    logger.error("DEFAULT_FROM_EMAIL missing and message has no from_email.")
                    continue

                to_emails = [addr for addr in (m.to or []) if addr]
                if not to_emails:
                    logger.warning("Email has no recipients. Skipping.")
                    continue

                payload = {
                    "sender": {"name": "Rooms4You", "email": from_email},
                    "to": [{"email": addr} for addr in to_emails],
                    "subject": m.subject or "",
                    "textContent": m.body or "",
                }

                # Use HTML if present
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

                # Sandbox mode -> Brevo returns success but does NOT deliver
                if sandbox:
                    payload["headers"] = {"X-Sib-Sandbox": "drop"}

                logger.info("Brevo send requested to=%s subject=%s sandbox=%s", to_emails, m.subject, sandbox)

                req = urllib.request.Request(
                    self.API_URL,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                    if 200 <= resp.status < 300:
                        sent_count += 1
                        logger.info("Brevo send OK status=%s response=%s", resp.status, body[:300])
                    else:
                        logger.error("Brevo send FAILED status=%s response=%s", resp.status, body[:500])

            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                logger.error("Brevo HTTPError %s: %s", e.code, err_body[:800])
                if not self.fail_silently:
                    raise

            except Exception as e:
                logger.exception("Brevo send exception: %s", e)
                if not self.fail_silently:
                    raise

        return sent_count

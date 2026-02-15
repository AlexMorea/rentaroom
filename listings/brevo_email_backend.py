import json
import os
import urllib.request
from django.core.mail.backends.base import BaseEmailBackend


class BrevoEmailBackend(BaseEmailBackend):
    """
    Django EmailBackend that sends emails via Brevo HTTP API.
    Works on Render free tier (no SMTP needed).
    """

    API_URL = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        api_key = os.environ.get("BREVO_API_KEY", "").strip()
        if not api_key:
            # No API key configured -> nothing sent
            return 0

        sandbox = os.environ.get("BREVO_SANDBOX", "0").strip().lower() in ("1", "true", "yes", "on")

        sent_count = 0
        for m in email_messages:
            try:
                from_email = (m.from_email or os.environ.get("DEFAULT_FROM_EMAIL") or "").strip()
                if not from_email:
                    # Brevo requires a sender email
                    continue

                # m.to is a list of recipient emails
                to_list = [{"email": addr} for addr in (m.to or []) if addr]

                # Build payload
                payload = {
                    "sender": {
                        "name": "Rooms4You",
                        "email": from_email,
                    },
                    "to": to_list,
                    "subject": m.subject or "",
                    # Django password reset uses body text by default
                    "textContent": m.body or "",
                }

                # If Django builds alternatives (html), use the html version too
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

                # Brevo sandbox mode: doesn't actually deliver email, but returns success
                if sandbox:
                    payload["headers"] = {"X-Sib-Sandbox": "drop"}

                req = urllib.request.Request(
                    self.API_URL,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=20) as resp:
                    if 200 <= resp.status < 300:
                        sent_count += 1

            except Exception:
                if not self.fail_silently:
                    raise

        return sent_count

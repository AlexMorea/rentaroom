# SMS OTP via Twilio Verify

Phone verification codes are sent by **SMS through Twilio's Verify API**
when Twilio credentials are present, and fall back to **email OTP**
automatically when they aren't (local dev) or when a send fails (Twilio
outage). Nothing is ever hard-blocked on Twilio.

## How it works in the code

| Piece | File |
| --- | --- |
| Twilio wrapper (`start_verification`, `check_verification`) | `listings/services/sms.py` |
| Channel dispatch + fallback (`_send_account_otp`, `_verify_account_otp`) | `listings/views/auth_views.py` |
| Settings / feature flag | `rentaroom/settings.py` (`SMS_OTP_ENABLED`) |
| Tests | `listings/tests_sms_otp.py` |

Twilio Verify owns the whole code lifecycle - generation, the SMS body,
expiry (~10 min), max attempts, and Fraud Guard against SMS-pumping. We
only call *start* (send a code) and *check* (is this code correct?). We do
**not** store the SMS code; the `PhoneOTP` table is only used on the email
fallback path.

Flows that now prefer SMS:
- Sign-up verification (`/register/` -> `/verify-account/`)
- The "verify your phone" gate on login for an unverified account
- Resend code button
- Change-phone-number (`/change-phone/` -> `/confirm-phone/`)

Email-change still verifies by email (that's the point of it).

## One-time Twilio setup

1. Create a Twilio account (the free trial is fine to start).
2. **Console → Verify → Services → Create new** (name it e.g. "Rooms4You").
   Copy the **Service SID** (starts with `VA...`).
3. From the Console dashboard copy the **Account SID** (`AC...`) and
   **Auth Token**.
4. Trial-account limit: SMS only reaches numbers you've added under
   **Phone Numbers → Verified Caller IDs**. Add your own cell there to
   test end-to-end. Upgrading (adding ~$20 credit) removes this and the
   "Sent from your Twilio trial account" prefix.
5. South Africa delivery: Verify uses Twilio's managed sender pool, so no
   sender-ID registration is needed to start. If delivery rates look poor
   later, look at a Messaging Service / registered Alphanumeric Sender ID
   for ZA in the Twilio console.

## Turning it on

Set these env vars (locally in `.env`, in production on Render):

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_VERIFY_SERVICE_SID=VA...
SMS_OTP_ENABLED=1
```

`SMS_OTP_ENABLED` only actually engages when all three credentials are
also set. To roll back instantly without deleting credentials, set
`SMS_OTP_ENABLED=0` (or clear it) - the app reverts to email OTP on the
next request, no redeploy needed.

## Cost

Twilio Verify bills roughly **$0.05 per successful verification** plus the
per-SMS carrier fee (ZA mobile ≈ $0.04–0.09). Budget ~$0.10–0.15 per
verified signup. Fraud Guard is included and blocks the main abuse vector
(bots triggering paid SMS to premium ranges).

## Testing locally without spending anything

Leave the Twilio vars blank - OTPs go to the console email backend as
today. `listings/tests_sms_otp.py` covers the SMS path with the Twilio
calls mocked, so `python manage.py test` never hits the network.

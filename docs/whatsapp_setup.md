# WhatsApp Business notifications - setup guide

The code for this is already live in the app (`utils/whatsapp.py`) and is a
pure no-op until you complete the steps below. Nothing here costs money to
set up - the only real cost is a small per-message fee once you're actually
sending, and only past a monthly free allowance. There is no monthly
platform fee: this integrates directly with Meta's own WhatsApp Business
Platform (the "Cloud API"), not a paid middleman.

## Why this path, not a third-party provider

- **Direct Meta Cloud API (what's built here):** free to integrate, no
  monthly platform fee. You pay Meta only per conversation once you're past
  the free monthly allowance, and "Utility"/"Authentication" template
  categories (OTP codes, order-style updates - which is everything wired in
  today) are Meta's cheapest tiers.
- **A paid reseller (Twilio, 360dialog, Wati, etc.):** adds either a
  markup per message or a flat monthly fee on top of the exact same
  underlying Meta cost, in exchange for an easier setup UI. Given there's no
  budget for that right now, going direct is the better fit - the trade-off
  is you do the (one-time, ~30-60 min) setup yourself below instead of a
  vendor doing it for you.
- **The plain WhatsApp Business app** (what most small businesses use)
  cannot be triggered from code at all - every message needs a human to tap
  send. Not usable for automated OTPs/notifications.

## Step 1: Meta Business Manager

1. Go to [business.facebook.com](https://business.facebook.com) and create a
   Business Portfolio for Rooms4You / 4You (Pty) Ltd if you don't have one.
2. Business verification (uploading company documents) is **not** required
   to start testing, but Meta will eventually ask for it before you can
   message phone numbers that aren't pre-registered test recipients. Start
   the verification early since it can take a few days to a couple of
   weeks - do this in parallel with everything else below, not after.

## Step 2: Create a WhatsApp Business Platform app

1. Go to [developers.facebook.com](https://developers.facebook.com) → **My
   Apps** → **Create App** → choose **Business** as the app type.
2. Add the **WhatsApp** product to the app.
3. Under WhatsApp → **API Setup**, Meta gives you a **free test number** and
   a temporary access token immediately - enough to send real messages to up
   to 5 verified test recipient numbers (add your own cellphone as one) with
   zero cost and zero waiting. Use this to test everything below before
   going live.
4. When ready for production, add your **real business phone number** under
   WhatsApp → **Phone Numbers**. It must be a number that is *not* already
   active on regular WhatsApp or WhatsApp Business app (you'll verify it by
   SMS/voice code during this step, and Meta takes over as its WhatsApp
   identity from here on - it can no longer be used in the consumer app).
5. Generate a **permanent access token**: System Users (Business Settings →
   Users → System Users) → create one → generate a token scoped to your
   WhatsApp app with `whatsapp_business_messaging` permission, no expiry.
   (The token shown in API Setup by default expires in 24h - fine for
   testing, not for production.)

## Step 3: Create the message templates

Go to WhatsApp Manager → **Message Templates** → **Create Template** for
each of the following. Category matters for cost - use **Utility** for all
of these (cheaper than Marketing, and these aren't promotional). Submit the
exact body text below (Meta reviews and usually approves Utility templates
within minutes to a few hours - vague/marketing-sounding copy is the most
common rejection reason, so keep it this literal).

| Template name (must match exactly) | Category | Body |
|---|---|---|
| `account_otp` | Authentication | Meta has a dedicated **Authentication** category with its own guided flow in the UI - pick that, not Utility, and it'll generate the OTP-with-copy-button format for you. Just set the code variable. |
| `device_otp` | Authentication | Same as above - this is the "new device sign-in" code. |
| `welcome` | Utility | `Welcome to Rooms4You, {{1}}! Your account is verified. Browse rooms or list your first one at rooms4you.co.za` |
| `waitlist_room_available` | Utility | `Good news! "{{1}}" just became available on Rooms4You. Contact the landlord now before someone else does: rooms4you.co.za` |
| `move_in_confirmation` | Utility | `Reminder: please confirm your move-in for "{{1}}" on Rooms4You so we can close out the placement. Log in to confirm.` |
| `placement_stalled` | Utility | `Your enquiry on "{{1}}" hasn't moved forward in a while. Log in to Rooms4You to update its status or follow up.` |

If you'd rather use different names, that's fine - just set the matching
`WHATSAPP_TEMPLATE_*` env var in Step 4 to whatever you actually named it in
Meta Business Manager.

## Step 4: Set the environment variables (Render)

Once you have a phone number and a permanent token, set these in Render's
environment settings for the web service (and any worker/cron that runs the
management commands):

```
WHATSAPP_ACCESS_TOKEN=<the permanent system-user token from Step 2.5>
WHATSAPP_PHONE_NUMBER_ID=<from WhatsApp Manager > API Setup - NOT the phone number itself, a numeric ID>
```

That's it - the moment both are set, every already-wired touchpoint (account
OTP, new-device OTP, welcome, waitlist notifications, move-in nudges,
stalled-placement nudges) starts sending over WhatsApp automatically,
alongside the existing email. No deploy of new code is needed for this step;
only the config change.

Only set `WHATSAPP_TEMPLATE_*` env vars if you named a template differently
from the table above - the defaults already match it.

## Testing before you're verified

While your WhatsApp Business app is still in development mode (before full
Business Verification), you can only message the up-to-5 test recipient
numbers you added in Step 2.3. Add your own number there and:

1. Set the env vars above using the test number's phone number ID and
   temporary token from API Setup.
2. Register a test tenant account using your own cellphone number as its
   `phone_number` - you should get the OTP over WhatsApp within seconds.

Once Business Verification completes and your real number is added, switch
the env vars to the real number's ID + the permanent token and it works the
same way for every real user.

## What's already wired in the code, and why not everything

See `PROJECT_OVERVIEW.md` §10 for the full list. Deliberately **not**
wired: the weekly landlord digest and stale-listing nudges. Those are
broad, less time-critical, and read closer to "Marketing" category under
Meta's rules (which costs more per message and needs the recipient to have
opted in specifically to marketing messages, not just to using the app) - not
worth doing until the OTP/utility rollout above has proven itself and there's
a case for the extra cost and consent flow.

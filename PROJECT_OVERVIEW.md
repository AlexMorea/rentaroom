# Rooms4You — System Documentation

> Internal reference. Architecture, data model, features and operations of the
> Rooms4You rental marketplace. Generated from the `main` branch; the code is
> authoritative. Model field lists and settings are abbreviated for readability.
> Business figures (membership prices, fee bands) reflect the values in the code
> at time of writing and should be checked against current commercial terms.

Rooms4You is a South African room-rental and short-stay marketplace, built by
4You (Pty) Ltd, that connects tenants with landlords, earns only on successful
placements, and puts trust and safety at the centre of the product. It is a
Django web application in public beta, deployed as a single web service with a
progressive-web-app front end and thin native shells for the app stores.

**Stack:** Django 5.2.7 · Python 3 / WSGI · PostgreSQL (SQLite in dev) · Render
hosting · Cloudinary media · Brevo email · Twilio Verify (optional) · PWA + TWA /
iOS shell · rooms4you.co.za

---

## Contents

1. [What Rooms4You is](#1-what-rooms4you-is)
2. [Business model & money flow](#2-business-model--money-flow)
3. [System architecture](#3-system-architecture)
4. [Application modules](#4-application-modules)
5. [Data model](#5-data-model)
6. [Request lifecycle & middleware](#6-request-lifecycle--middleware)
7. [Ranking & listing quality](#7-ranking--listing-quality)
8. [Trust & safety pipeline](#8-trust--safety-pipeline)
9. [Accounts, auth & verification](#9-accounts-auth--verification)
10. [Notifications: email & web push](#10-notifications-email--web-push)
11. [Background jobs & commands](#11-background-jobs--commands)
12. [SEO & PWA](#12-seo--pwa)
13. [Deployment & configuration](#13-deployment--configuration)
14. [Local development](#14-local-development)
15. [Testing & load](#15-testing--load)
16. [Mobile apps](#16-mobile-apps)
17. [Appendix: route map](#17-appendix-route-map)

---

## 1. What Rooms4You is

Rooms4You is an online-only marketplace where South African landlords list rooms
to rent and tenants find, contact and move into them.

### Who uses it

- **Tenants** — search and filter listings, save favourites, message landlords,
  leave reviews, book short stays, and use the safety tools when going to a
  viewing.
- **Landlords** — publish and maintain listings (subject to a membership tier),
  see per-listing analytics, manage enquiries, and progress a matched tenant
  through to a confirmed move-in.
- **Guest-house / BnB hosts** — list nightly-rate accommodation with a real
  availability calendar and accept or decline date requests.
- **Bakkie (moving) drivers** — register a vehicle, get verified, and take
  moving-day bookings from tenants.
- **Staff / Trust & Safety** — triage fraud reports, verify landlords, approve
  membership payments, and reconcile success-fee invoices, mostly through Django
  admin plus a few purpose-built staff dashboards.

### What makes it distinct

- **Success-fee economics.** The platform only bills a placement fee once a
  tenant has actually moved in (confirmed by both sides), and a booking fee only
  once a stay is confirmed. It never touches tenant deposits or rent.
- **Listings that stay honest.** Landlords are nudged to re-confirm availability
  every two weeks; unconfirmed listings are demoted in ranking and eventually
  auto-hidden.
- **Visible trust signals.** Admin-verified landlord badges, measured (not
  self-reported) response times, a real fraud-report pipeline with staff
  alerting, and a Trust Centre of safety guidance.
- **Safety at the viewing.** A "Guardian" companion mode shares live location
  with an emergency contact and has a panic button.

---

## 2. Business model & money flow

Two revenue lines, both reconciled manually — there is no payment gateway in the
codebase. Users pay by EFT and upload proof; staff confirm and flip a status.

### Landlord membership tiers

Every landlord gets a 30-day free trial (`Membership.is_trial`, `trial_end`).
After that, listing capacity is gated by tier. Payment is
*request → upload proof of payment → admin approves*
(`mark_payment_submitted` → `activate_membership`).

| Tier        | Code      | Listing limit | Indicative price     |
|-------------|-----------|---------------|----------------------|
| Starter4You | `starter` | 2             | Free (trial default) |
| Bronze4You  | `bronze`  | 5             | R49                  |
| Silver4You  | `silver`  | 10            | R99                  |
| Gold4You    | `gold`    | Unlimited     | R199                 |

`Membership.can_create_listing()` is the gate: it blocks inactive accounts,
expired trials, and accounts with a payment still pending. `MembershipMiddleware`
deactivates a landlord the moment their trial lapses.

### Success fees — room placements

A `Placement` tracks one tenant + one room from first interest to move-in. When
both parties confirm the move-in, status goes to *Success Fee Due* and a
`PlacementInvoice` is generated. Fee bands (`Placement.calculate_success_fee`),
by monthly rent:

| Monthly rent      | Success fee |
|-------------------|-------------|
| Up to R1,500      | R100        |
| R1,501 – R2,500   | R150        |
| R2,501 – R4,000   | R250        |
| Above R4,000      | R350        |

### Success fees — guest-house bookings

When a host confirms a booking, a `BookingInvoice` is raised for **8% of the
estimated booking value, minimum R50** (`Booking.expected_success_fee`).
Confirmation is the billable signal for a stay (a booked check-in date is
unambiguous), unlike a room placement which needs the separate dual move-in
confirmation.

> **Guardrail.** Automatic suspension of landlords for overdue success fees
> exists (`Membership.suspend_for_unpaid_placement_fee`,
> `flag_overdue_placement_fees`) but is gated behind `PLACEMENT_FEE_AUTO_SUSPEND`,
> which defaults to off. Until deliberately switched on, the job only reports
> what it *would* do.

---

## 3. System architecture

A conventional Django monolith: one WSGI application, one relational database,
external SaaS for the three things it should not run itself — image hosting,
email delivery, and SMS verification. Everything asynchronous is optional and
currently dormant.

```
CLIENTS                    RENDER WEB SERVICE                 STORES & SERVICES
┌──────────────┐           ┌─────────────────────────┐        ┌───────────────────────────┐
│ Browser      │──HTTPS──▶ │ gunicorn                │        │ PostgreSQL (SQLite dev)    │
│ Installed PWA │──────────▶│ WhiteNoise · static     │──ORM──▶│                           │
│ Android TWA  │──────────▶│ Middleware chain        │        │ Redis — cache/broker (opt)│ (dashed)
│ / iOS shell  │           │  www 301 · auth ·       │· · · ·▶│                           │
└──────────────┘           │  membership · cache hdr │        │ Cloudinary — images       │
                           │ ┌─────────────────────┐ │───────▶│ Brevo — transactional mail│
                           │ │ Django apps · views │ │───────▶│ Twilio Verify — SMS (opt) │ (dashed)
                           │ └─────────────────────┘ │· · · ·▶│ Google — OAuth, Maps      │
                           │ LocMem cache (60s)      │───────▶└───────────────────────────┘
                           └─────────────────────────┘
                           ┌─────────────────────────┐
                           │ Celery worker + beat     │  dormant until CELERY_BROKER_URL is set
                           │ (scores/stale/digest/…)  │
                           └─────────────────────────┘
```

Solid paths are always on; dashed paths are wired but inactive until the
corresponding environment variable is configured. The web service serves its own
static assets through WhiteNoise; only user-uploaded images go to Cloudinary.

### Component responsibilities

| Component      | Role                                                                 | Config key            |
|----------------|---------------------------------------------------------------------|-----------------------|
| gunicorn       | WSGI server on Render                                                | `rentaroom.wsgi`      |
| WhiteNoise     | Compressed, hashed static-file serving (`CompressedManifestStaticFilesStorage`) | `STORAGES` |
| PostgreSQL     | Primary datastore in production; SQLite file locally                 | `DATABASE_URL`        |
| Cloudinary     | All room / guest-house / vehicle / proof-of-payment images; deletes cascade via `post_delete` signals | `CLOUDINARY_*` |
| Brevo          | Transactional email over HTTPS API (no SMTP, Render-free-tier friendly) | `BREVO_API_KEY`    |
| Twilio Verify  | SMS OTP channel for onboarding; falls back to email OTP when unset   | `TWILIO_*`            |
| Redis          | Shared cache and Celery broker when present; LocMem otherwise        | `REDIS_URL`           |
| Celery + beat  | Scheduled scoring, freshness sweeps, digests, response-time stats    | `CELERY_BROKER_URL`   |
| Google         | Sign-In token verification (`oauth2.googleapis.com/tokeninfo`) and Maps JS for the pin picker | `GOOGLE_MAPS_API_KEY` |

---

## 4. Application modules

Six domain apps plus the project config package. Each app owns its models, URLs,
views, admin and tests. Cross-app coupling is deliberate and narrow — e.g.
`placements` and `trust` both reference `listings.Room`, but nothing reaches into
another app's view layer.

| App          | Path (role)                     | Owns |
|--------------|---------------------------------|------|
| **listings** | `listings/` — the core app      | Rooms, room images, reviews, favourites, contact tracking, in-app messaging, the tenant-facing search page, the landlord dashboard and analytics, user `Profile`, email/phone OTP models, SEO helpers, sitemaps, the Brevo email backend, and the public marketing pages (home, about, terms, privacy, safety). |
| **accounts** | `accounts/` — membership & identity | The `Membership` model and tier logic, membership payment + admin-approval flow, `MembershipMiddleware`, the `PushSubscription` model and Web Push send pipeline, VAPID key handling, a state engine that decides post-login routing, and device-recognition helpers. |
| **placements** | `placements/` — the placement pipeline | The `Placement` sales pipeline (interested → viewing → approved → moved-in), dual move-in confirmation, `PlacementInvoice` success-fee billing, an append-only `PlacementStatusHistory` audit trail written by signal, and landlord / tenant placement dashboards. |
| **stays**    | `stays/` — short-stay bookings  | The `GuestHouse` nightly-rate model, images, an availability engine (`stays/availability.py`) with request-vs-confirm semantics, `Booking` and `BlockedDate`, host accept/decline with auto-decline of overlapping requests, and `BookingInvoice`. |
| **trust**    | `trust/` — Trust & Safety       | The unified `FraudReport` model (listing-specific and general), a `post_save` signal that emails the safety team (flagging repeat offenders), and the Trust Centre content pages. |
| **services** | `services/` — safety & moving   | Guardian companion sessions with location pings and panic alerts, emergency contacts and events, plus the Bakkie side: `BakkieDriver` registration and verification, availability toggles, `MoveBooking`, and a service-analytics event log. |

- **rentaroom/** — project package: `settings.py`, URL root, WSGI/ASGI, Celery
  app, and the `WWWRedirectMiddleware`.
- **utils/ · services.py** — shared helpers: `utils/email.py`
  (`send_template_email`), `listings/services.py` (sitewide stats aggregation).
- **core/** — holds a `cleanup_users` maintenance command; not in
  `INSTALLED_APPS`.

---

## 5. Data model

All models use `BigAutoField` primary keys. Auth is Django's built-in `User`;
every user has exactly one `listings.Profile` (created by a `post_save` signal
and defensively in middleware).

### listings

| Model        | Purpose                                   | Notable fields |
|--------------|-------------------------------------------|----------------|
| `Room`       | A room-to-rent listing (monthly)          | title, price, deposit_amount, location/suburb/town/city/province, lat/long, room_type (8 choices), total_units / available_units / availability_status, is_available, `hits`, `score`, `last_confirmed_at`, `last_nudge_sent_at` |
| `RoomImage`  | Ordered Cloudinary images (max 10)         | image, order; `post_delete` removes from Cloudinary |
| `Profile`    | Per-user profile / role                    | role (tenant/landlord), persona, is_email_verified, is_phone_verified, is_verified_landlord, country_code, phone_number, GPS capture fields, POPIA consent timestamps, `avg_response_minutes` / `response_rate_percent` / `responses_measured` |
| `Review`     | Tenant rating of a room (1–5)              | rating, comment; unique per (room, user) |
| `Favorite`   | Tenant "saved" room                        | unique per (user, room) |
| `Contact`    | Tenant expressed contact with a room       | unique per (room, user) |
| `Message`    | In-app messaging thread rows               | room, sender, recipient, body, is_read |
| `RoomStat`   | Analytics events (view / contact… / success) | stat_type, optional user, GPS + suspicion fields; indexed (room, stat_type) |
| `PhoneOTP`   | One active OTP per user                    | otp, 15-min expiry; save() clears prior unverified OTPs |

### accounts

| Model              | Purpose                            | Notable fields |
|--------------------|------------------------------------|----------------|
| `Membership`       | One landlord's plan & billing state | tier, status (active/pending/suspended), is_trial, trial_end, payment_requested, requested_tier, proof_of_payment, approved_by/at, `membership_id` |
| `PushSubscription` | One browser/device Web Push endpoint | endpoint (unique), p256dh, auth, user_agent — several per user allowed |
| `TrustedDevice`    | A device that has cleared a login challenge | SHA-256 `token_hash` of a 90-day `httponly` cookie, label, last_seen_at (`accounts/devices.py`) |

### placements

| Model                    | Purpose                          | Notable fields |
|--------------------------|----------------------------------|----------------|
| `Placement`              | Tenant × room journey to move-in | status (9 states), viewing_date, move_in_date, tenant/landlord_confirmed_move_in (+timestamps), unique per (tenant, room), FKs `PROTECT` |
| `PlacementInvoice`       | Success-fee invoice (1:1)        | amount, status (pending/paid/waived), payment_reference, marked_paid_by; `mark_paid()` also closes the placement |
| `PlacementStatusHistory` | Append-only audit trail          | from_status, to_status, changed_by (null = system); written only by signal |

### stays

| Model             | Purpose                     | Notable fields |
|-------------------|-----------------------------|----------------|
| `GuestHouse`      | Nightly-rate accommodation  | price_per_night, max_guests, min_nights, check-in/out times, amenity booleans, is_active |
| `GuestHouseImage` | Ordered images (max 15)     | image, order |
| `Booking`         | A guest's date request      | check_in / check_out, num_guests, status (requested…completed), `nights`, `total_estimate`, `expected_success_fee` (8%, min R50) |
| `BlockedDate`     | Host-blocked range          | start_date, end_date, reason |
| `BookingInvoice`  | Booking success-fee invoice (1:1) | amount, status, payment_reference |

### trust & services

| Model                                             | Purpose | Notable fields |
|---------------------------------------------------|---------|----------------|
| `trust.FraudReport`                               | Scam / safety report, listing-tied or general | category (10), status (new/investigating/resolved/dismissed), reporter (nullable), room (nullable), reported_user, `reference_code` (R4Y-000001), `is_repeat_offender` |
| `services.GuardianSession`                        | Live-location safety session | destination, emergency contact, status (active/ended/panic), latest lat/long |
| `services.GuardianLocationPing / PanicAlert / EmergencyEvent` | Session telemetry & alerts | lat/long, resolved flags |
| `services.BakkieDriver`                           | Moving-truck driver profile | vehicle_type, registration, licence image, application_status, is_verified, availability_status, rating |
| `services.MoveBooking`                            | Tenant→driver moving job | pickup / dropoff, scheduled_time, quoted_price, status, payment_status |
| `services.EmergencyContact / ServiceAnalyticsEvent` | Contacts & event log | relationship; event_type + JSON metadata |

---

## 6. Request lifecycle & middleware

The middleware order in `settings.MIDDLEWARE` is load-bearing. A request passes
through these in order:

1. **SecurityMiddleware** — HSTS, SSL redirect (production only; skipped under
   `manage.py test`), nosniff, referrer policy.
2. **WhiteNoiseMiddleware** — serves hashed static assets directly.
3. **WWWRedirectMiddleware** — 301s any non-canonical host to
   `https://www.rooms4you.co.za`; no-ops for localhost, `testserver`, and
   `*.onrender.com`.
4. Sessions → Common → CSRF → Authentication → Messages (session-backed storage).
5. **MembershipMiddleware** — guarantees a `Profile` exists, and deactivates
   landlords whose trial has expired.
6. Clickjacking (`X-Frame-Options: DENY`).
7. **DisableCacheMiddleware** — sets `Cache-Control: public, max-age=60` on
   anonymous cookie-less GET/HEAD responses (matching the server-side cache TTL),
   and `no-store` on everything authenticated.

### Caching strategy

The room list (`room_list` view) is the most-hit page — every first visit,
social click and Google crawl. It caches *matching room IDs*, not rendered HTML,
for 60 seconds, because the navbar carries a session-bound CSRF logout form and
caching HTML would risk cross-session token bleed. The queryset is rebuilt from
cached IDs so pagination still works normally. "Popular" room IDs and the
distinct-locations list are cached separately (5 min / 1 hour). AJAX filter
refreshes have their own 60s JSON-payload cache. Cache backend is Redis when
`REDIS_URL` is set, otherwise per-process LocMem (so multi-worker deployments
should run Redis for a shared cache).

### Analytics writes

`room_detail` increments a denormalised `Room.hits` counter with an `F()`
expression, and writes a `RoomStat` "view" row off the request path — via a
Celery task if a broker is configured, otherwise a daemon thread deferred to
`transaction.on_commit` so it can't deadlock against an open test transaction.

---

## 7. Ranking & listing quality

Default "best match" ordering is by a materialised `Room.score` integer,
recomputed in batches by the `compute_scores` command (hourly under Celery beat).
Other sorts (newest, price) bypass the score.

### Score formula

| Term            | Weight | Notes |
|-----------------|--------|-------|
| hits            | × 3    | denormalised page-view counter |
| distinct views  | × 1    | RoomStat "view" rows |
| contacts        | × 8    | RoomStat "contact*" rows — the strongest intent signal |
| favourites      | × 2    | |
| review quality  | × 3    | of `(sum of ratings − 3 × review count)` — centred on 3, so poor reviews subtract |
| staleness       | − 2/day | per day overdue past `LISTING_STALE_DAYS`, capped at 60 days |

The result is floored at 0. Rooms with `score ≥ POPULAR_SCORE_THRESHOLD`
(default 100) qualify for the "Popular" rail.

### Listing freshness

Every `Room` tracks `last_confirmed_at`. It resets to "now" whenever the landlord
edits the listing, toggles vacancy, clicks "Still accurate? Confirm", or acts on
a one-click signed link in a nudge email/push. The lifecycle
(`flag_stale_listings`, daily):

| Days since confirmed | Effect | Setting |
|----------------------|--------|---------|
| ≥ 14 | Marked *stale*: ranking penalty begins; "please confirm" email + push nudge (re-sent at most every 14 days) | `LISTING_STALE_DAYS` |
| ≥ 30 | Auto-hidden (`is_available = False`); landlord gets a one-click reactivate link — a soft hide, never a delete | `LISTING_AUTO_HIDE_DAYS` |

### Other quality signals

- **Response time** — `compute_response_stats` measures the median time from a
  tenant's first message to the landlord's first reply across real threads. Below
  3 measured threads no public label is shown; at/above it, labels range from
  "Usually responds within an hour" to "Response time varies", plus an
  `is_fast_responder` flag (≤ 4h and ≥ 70% response rate).
- **Completeness** — computed live on the landlord's own dashboard: 3+ photos, a
  30-word description, a map pin, a WhatsApp number, and a full street address,
  shown as a percentage with the missing items listed.

---

## 8. Trust & safety pipeline

"We investigate reports" is a promise the product has to keep, so a report is
never allowed to just sit in the admin.

- **Two entry points, one model.** A "Report listing" form on a room and a
  general "Report Fraud" form in the Trust Centre both write `FraudReport`.
  Reporters do not need an account (`reporter` is nullable, with a free-text
  contact field).
- **Staff alerting.** A `post_save` signal emails `SAFETY_TEAM_EMAIL` (default
  `safety@rooms4you.co.za`) on every new report. Failure is logged, never raised,
  so a broken mailer can't block the report being saved.
- **Repeat-offender escalation.** `related_open_reports` finds other open reports
  against the same room or user; if any exist the alert subject is prefixed
  `🚨 REPEAT`.
- **Case references.** Each report gets an `R4Y-000001` reference to hand back to
  the reporter; resolving a report pushes a web-push notification to the reporter
  if they were logged in.
- **Verification.** `Profile.is_verified_landlord` is an admin-set badge surfaced
  on listings and landlord profiles. Real phone verification is listed as
  "Coming Soon" on the Trust Centre — the current `is_phone_verified` flag is set
  from the same email OTP and is not surfaced as a separate signal.
- **Guardian mode.** Before a viewing a tenant starts a `GuardianSession` with a
  destination and emergency contact; the browser posts location pings, and a
  panic button raises a `PanicAlert` / `EmergencyEvent`.

---

## 9. Accounts, auth & verification

Django session auth, extended with an OTP onboarding step, optional Google
sign-in, and new-device challenges. The custom login view lives in
`listings/views/auth_views.py`.

### Registration & OTP

- Sign-up creates the `User` (active) and a `PhoneOTP`, then emails a code.
  `verify_account` confirms it and sets `is_email_verified` / `is_phone_verified`.
- OTP delivery is email by default; if `TWILIO_*` credentials and
  `SMS_OTP_ENABLED` are set, onboarding OTP goes over Twilio Verify SMS instead,
  with email as fallback.
- Resend is rate-limited (90 s cooldown, cache-keyed per user).
- Email-change and phone-change flows each re-verify with a fresh OTP;
  `pending_email` + a UUID token guard the change.

### Google sign-in

The client obtains a Google ID token; the server verifies it against
`oauth2.googleapis.com/tokeninfo`, then either links an existing account by email
or creates one and routes new users through a "complete your profile" form
(`GoogleCompleteProfileForm`).

### Abuse protection

| Control              | Limit                              | Rationale |
|----------------------|------------------------------------|-----------|
| IP login counter     | cache-keyed per IP                 | One machine / botnet node hammering many accounts |
| Account login counter | 7 attempts, 30-min lockout        | Targeted credential-stuffing on one known email, spread across IPs |
| New-device OTP       | email challenge on unrecognised device | `accounts/devices.py` — `is_known_device` / `remember_device` |
| Password-reset       | `RateLimitedPasswordResetView`     | Throttles reset-email spam |
| Open-redirect guard  | `url_has_allowed_host_and_scheme`  | Validates every `?next=` before redirecting |

### Post-login routing

`accounts/state_engine.py` is the single source of truth: unauthenticated →
login; unverified → verify-account; then by role — landlord → dashboard, driver →
Bakkie home or driver dashboard (by verification), tenant → room list. A
validated `?next=` overrides the role default.

---

## 10. Notifications: email & web push

Lifecycle events are delivered as an email + a web-push notification in tandem,
so a landlord who has enabled neither still gets one.

### Email

- **Backend.** `BrevoEmailBackend` (`listings/email_backend.py`) posts to the
  Brevo HTTPS API — chosen because Render's free tier blocks outbound SMTP.
  Falls back to Django's console backend when `BREVO_API_KEY` is unset.
- **Templates.** HTML emails under `listings/templates/emails/`: listing-live,
  confirm-availability nudge, auto-hidden notice, weekly landlord digest, staff
  fraud-report alert, OTP and new-device codes, welcome.
- **Sender identity.** A BIMI-compliant vector logo is served for the
  Gmail/Yahoo sender avatar; `DEFAULT_FROM_EMAIL` / `DEFAULT_FROM_NAME`
  configurable.

### Web push

- VAPID keys from `VAPID_PRIVATE_KEY_PEM` / `VAPID_PUBLIC_KEY`; an ephemeral pair
  is generated in DEBUG/tests, and production degrades gracefully to a no-op if
  keys are missing rather than crashing.
- `PushSubscription` stores one row per browser/device; `accounts.push.notify_user()`
  fans out to all of a user's subscriptions.
- Client side: `static/js/push-notify.js` + a subscribe banner;
  subscribe/unsubscribe endpoints under `/accounts/push/`.
- The Android TWA delegates native notification permission to the same Web Push
  subscriptions — no FCM/APNs server keys needed.

---

## 11. Background jobs & commands

Every scheduled task ships `force=False` (report-only) by default. Nothing that
emails users, hides listings or mutates a score does so until run with `--force`
(or its Celery task called with `force=True`).

### Celery beat schedule

| Task                        | Cadence     | Does |
|-----------------------------|-------------|------|
| `compute_scores_task`       | hourly      | Recompute materialised `Room.score` |
| `flag_stale_listings_task`  | daily 06:00 | Nudge / auto-hide unconfirmed listings |
| `send_landlord_digest_task` | Mon 08:00   | Per-landlord weekly performance + tips email/push |
| `compute_response_stats_task` | daily 06:30 | Recompute landlord response-time signal from Message threads |

> **Current state.** `CELERY_BROKER_URL` is unset, so `CELERY_BEAT_SCHEDULE` is
> effectively inert. Until a broker + worker + beat are deployed, these must be
> run as cron / one-off `manage.py` invocations.

### Management commands

| Command                       | App        | Purpose |
|-------------------------------|------------|---------|
| `compute_scores`              | listings   | Batch-recompute room scores (`--force` to write) |
| `backfill_hits`               | listings   | Rebuild the denormalised `hits` counter from RoomStat |
| `flag_stale_listings`         | listings   | Freshness nudges + auto-hide |
| `flag_landlords_without_listing` | listings | One-time nudge to landlords who signed up but never posted a room |
| `send_landlord_digest`        | listings   | Weekly landlord digest |
| `compute_response_stats`      | listings   | Landlord response-time stats |
| `generate_vapid_keys`         | accounts   | One-off VAPID keypair generation for production |
| `backfill_profiles`           | accounts   | Create missing `Profile` rows |
| `check_move_ins`              | placements | Trigger dual move-in confirmation when a move-in date passes |
| `flag_overdue_placement_fees` | placements | Report (or, if `PLACEMENT_FEE_AUTO_SUSPEND`, suspend) landlords with overdue success fees |
| `flag_stalled_placements`     | placements | Nudge placements stuck mid-pipeline |
| `flag_overdue_booking_fees`   | stays      | Report overdue guest-house booking fees |
| `cleanup_users`               | core       | Maintenance: prune incomplete/abandoned signups |

---

## 12. SEO & PWA

### Search

- **Canonical domain.** `https://www.rooms4you.co.za`, enforced by 301
  middleware; canonical tags, sitemap and robots all agree on it.
- **Sitemap.** `/sitemap.xml` — every available room (daily changefreq, priority
  0.8) plus 8 static pages.
- **robots.txt** served from a view; `/.well-known/assetlinks.json` served for
  Android TWA verification (currently an empty array until the signing
  fingerprint is set).
- **Structured data.** Sitewide `Organization` + `WebSite` (with `SearchAction`);
  per-room `Product` + `Offer` (ZAR price, in/out-of-stock, geo) +
  `BreadcrumbList`, and `AggregateRating` when reviews exist. The `ld_json()`
  helper escapes `< > &` so landlord-authored text cannot break out of the
  script tag.
- **Analytics hooks.** `GOOGLE_SITE_VERIFICATION` and `GA_MEASUREMENT_ID` are
  env-driven and picked up by the base template with no redeploy — both blank by
  default.

### Progressive web app

- `static/manifest.json` with `id`, categories, and shortcuts (Browse Rooms,
  List a Room); maskable icons at 192/512.
- Service worker at `/service-worker.js` (cache `v3`), a fully self-contained
  offline page, and a custom install banner that only appears on a real
  `beforeinstallprompt` with a 14-day dismiss cooldown.
- This PWA foundation is exactly what the Android TWA (Bubblewrap) and the iOS
  Capacitor shell load — there is no separate mobile web build.

---

## 13. Deployment & configuration

Single Render web service, auto-deployed from `main`. Configuration is entirely
environment variables; `python-dotenv` loads a local `.env` in development.

### Runtime

| Aspect | Detail |
|--------|--------|
| Server | gunicorn → `rentaroom.wsgi:application` |
| Static | `collectstatic` → WhiteNoise compressed manifest storage (checked-in `staticfiles/`) |
| DB     | Postgres via `DATABASE_URL` (SSL required, `conn_max_age=60`, health checks on); SQLite file when unset |
| Hosts  | `rooms4you.co.za`, `www.rooms4you.co.za`, `*.onrender.com`, plus `ALLOWED_HOSTS` extras |
| HTTPS  | SSL redirect + HSTS (1 year) + secure cookies when `DEBUG=0` and not under test; `X-Forwarded-Proto` trusted |

### Environment variables

| Variable | Required? | Effect |
|----------|-----------|--------|
| `SECRET_KEY` | prod (mandatory) | Startup fails without it when `DEBUG=0`; auto-generated & persisted to `.env` in dev |
| `DEBUG` | no (default 0) | `1` enables dev behaviour, disables SSL redirect / HSTS |
| `DATABASE_URL` | prod | Postgres DSN; SQLite fallback otherwise |
| `REDIS_URL` | no | Shared cache backend (else LocMem) |
| `CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET` | prod | Image upload + delivery |
| `BREVO_API_KEY` | prod | Switches email from console to Brevo API |
| `DEFAULT_FROM_EMAIL` / `DEFAULT_FROM_NAME` | no | Sender identity |
| `SAFETY_TEAM_EMAIL` | no | Where fraud-report alerts go |
| `TWILIO_ACCOUNT_SID` / `_AUTH_TOKEN` / `_VERIFY_SERVICE_SID` | no | Enables SMS OTP |
| `SMS_OTP_ENABLED` | no | Kill-switch (`0` forces email OTP) |
| `VAPID_PRIVATE_KEY_PEM` / `VAPID_PUBLIC_KEY` / `VAPID_CLAIMS_EMAIL` | prod (for push) | Web Push signing |
| `GOOGLE_MAPS_API_KEY` | no | Map pin picker |
| `GOOGLE_SITE_VERIFICATION` / `GA_MEASUREMENT_ID` | no | Search Console + GA4 |
| `CELERY_BROKER_URL` | no | Activates the beat schedule |
| `PLACEMENT_FEE_AUTO_SUSPEND` | no (default 0) | Arms automatic landlord suspension for overdue fees |
| `POPULAR_SCORE_THRESHOLD` / `USE_MATERIALIZED_SCORE` / `LISTING_STALE_DAYS` / `LISTING_AUTO_HIDE_DAYS` | no | Ranking & freshness tuning |
| `TWA_PACKAGE_NAME` / `TWA_SHA256_FINGERPRINTS` | no | Populate `assetlinks.json` once the Android app is signed |

---

## 14. Local development

| Step | Command |
|------|---------|
| Create / activate venv | `python -m venv venv` · `venv\Scripts\activate` |
| Install | `pip install -r requirements.txt` |
| Dev tools (optional) | `pip install -r requirements-dev.txt` |
| Migrate | `python manage.py migrate` |
| Seed data (optional) | `python manage.py loaddata data.json` |
| Superuser | `python manage.py createsuperuser` |
| Run | `python manage.py runserver` |

With no `.env` values set, the app runs fully offline: SQLite, console email,
ephemeral `SECRET_KEY` and VAPID keys, LocMem cache, email OTP. `DEBUG=1` also
disables the www redirect and serves `/media/` locally.

---

## 15. Testing & load

- **Unit / integration tests** live beside each app — `listings/tests_*.py` alone
  covers OTP, login, ranking, reviews, AJAX, image deletion, room creation,
  freshness, response time, verified badges and device verification;
  `placements`, `stays`, `trust`, `services` and `accounts` each carry their own
  suites.
- Settings detect `test` in `argv` (`RUNNING_TESTS`) and disable SSL redirect so
  the test client isn't 301'd before reaching views.
- **Load testing** — `locustfile.py` at the repo root (run with `locust`).
- **CI** — a GitHub Actions workflow (`.github/workflows/ci.yml`) runs the test
  suite on push.
- **Static analysis** — `pyrightconfig.json` is present; model files carry
  targeted `pyright: ignore` notes where Django's runtime is looser than the
  stubs.

---

## 16. Mobile apps

Both store presences wrap the live site — there is no forked mobile codebase to
keep in sync.

- **Android** (`mobile/android/`) — a pre-validated Bubblewrap / Trusted Web
  Activity config (`twa-manifest.json`, package `za.co.rooms4you.twa`) with
  notification delegation enabled. Remaining work is machine-side:
  `bubblewrap build`, capture the signing fingerprint, set `TWA_*` env vars so
  `assetlinks.json` verifies, then Play Console submission ($25 one-off,
  screenshots, content rating).
- **iOS** (`mobile/ios/`) — a Capacitor shell project (`capacitor.config.json`,
  Xcode project, app icons and splash assets) that loads the PWA.
- A store-submission checklist is tracked in the repo.

---

## 17. Appendix: route map

URL roots from `rentaroom/urls.py`.

| Prefix | Include | Representative routes |
|--------|---------|-----------------------|
| `/` | `listings.urls` | `/`, `/rooms/`, `/rooms/<pk>/`, `/rooms/new/`, `/rooms/<pk>/edit/`, `/dashboard/`, `/inbox/`, `/profile/`, `/login/`, `/register/`, `/verify-account/`, `/membership/`, `/about/ /contact/ /terms/ /privacy/ /safety/`, `/offline/` |
| `/accounts/` | `accounts.urls` | `/accounts/membership/<tier>/`, `/accounts/admin/memberships/`, `.../<pk>/approve\|reject/`, `/accounts/push/subscribe\|unsubscribe/` |
| `/services/` | `services.urls` | `/services/guardian/`, `.../start/ .../end/<id>/ .../ping/<id>/ .../panic/<id>/`, `/services/bakkie/`, `.../driver/dashboard/`, `.../booking/create/<driver_id>/` |
| `/trust/` | `trust.urls` | `/trust/`, `.../verification/ .../renting-safely/ .../stay-safe/ .../fraud-alerts/ .../report-fraud/ .../official-communication/` |
| `/placements/` | `placements.urls` | `/placements/landlord/`, `.../<id>/update/`, `/placements/tenant/`, `/placements/<id>/confirm-move-in/` |
| `/stays/` | `stays.urls` | `/stays/`, `/stays/<pk>/`, `/stays/new/`, `/stays/<pk>/book/`, `/stays/bookings/mine\|host/`, `/stays/bookings/<pk>/accept\|decline\|cancel/` |
| `/admin/` | `django.contrib.admin` | Full staff back-office — memberships, fraud reports, placements, invoices, listings |
| (root files) | — | `/sitemap.xml`, `/robots.txt`, `/service-worker.js`, `/.well-known/assetlinks.json` |

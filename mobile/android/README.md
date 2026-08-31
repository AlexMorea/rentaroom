# Rooms4You — Android app (Trusted Web Activity)

This wraps the live Rooms4You PWA (rooms4you.co.za) as an installable Android app
using [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap) and Google's
Trusted Web Activity (TWA) approach — a real Play Store app, backed by the same
Django site, no separate app codebase to maintain.

`twa-manifest.json` in this folder is a complete, pre-validated Bubblewrap
config (validated against `@bubblewrap/core`'s own parser — see git history/PR
description). It was hand-authored rather than produced by `bubblewrap init`
because generating the project requires downloading a JDK and the Android SDK,
which this development environment doesn't have. Everything below is what's
left to actually produce and ship the `.aab`.

## Prerequisites (do these once, on your own machine)

- Node.js 18+ (for the `bubblewrap` CLI)
- A JDK 17 — Bubblewrap can install one for you when asked
- The Android SDK — Bubblewrap can install this for you too

## 1. Build the Android project

```bash
npm install -g @bubblewrap/cli
cd mobile/android
bubblewrap build
```

The first run creates `./android.keystore` (referenced by `signingKey` in
`twa-manifest.json`) and asks for a keystore password — **write this password
down somewhere durable**. Losing it means you can never update this app again
under the same Play Store listing; you'd have to publish as a new app from
scratch.

This produces `app-release-signed.apk` and `app-release-bundle.aab` — the
`.aab` is what you upload to Play Console.

## 2. Get the SHA-256 fingerprint and wire up Digital Asset Links

```bash
keytool -list -v -keystore android.keystore -alias android
```

Copy the `SHA256:` fingerprint it prints, then set these two environment
variables in production (Render dashboard, or wherever `rooms4you.co.za` is
deployed):

```
TWA_PACKAGE_NAME=za.co.rooms4you.twa
TWA_SHA256_FINGERPRINTS=<the fingerprint from keytool, colons included>
```

This is what makes `https://www.rooms4you.co.za/.well-known/assetlinks.json`
(already implemented — `listings/views/static_pages.py::assetlinks_json`)
start returning real verification data instead of `[]`. **Without this step
the installed app opens links inside a visible browser bar instead of full-
screen** — the single most common reason a TWA looks "unfinished" after
launch.

## 3. Enable notification delegation (already wired on the Django side)

`enableNotifications: true` is already set in `twa-manifest.json`. This maps
native Android notification permission to the same Web Push subscriptions
built into the site (`accounts/push.py`, `static/js/push-notify.js`) — a user
who taps "Enable" inside the Android app gets the exact same push pipeline
already used on the web/PWA, no separate mobile push service (FCM server
keys, APNs, etc.) needed.

## 4. Play Console submission

You'll need, separately from this repo:

- A Google Play Developer account (**one-time $25 fee**, real ID
  verification — this is the step nobody but you can do)
- App icon (512×512), a feature graphic (1024×500), and 2+ phone
  screenshots — export these from the existing `static/images/icon-512.png`
  / `icon-maskable-512.png` plus fresh screenshots of the live site
- A privacy policy URL (Rooms4You already has one — link the `/privacy/`
  page)
- Content rating questionnaire (Play Console walks you through this)
- Store listing copy — short description, full description. Suggested short
  description, matching the current homepage/trust-centre positioning:

  > South Africa's trusted way to find a room to rent. Verified landlords,
  > safer viewings, and a success fee we only earn once you've actually
  > moved in.

Upload the `.aab` from step 1 under **Production → Create release**, fill in
the listing, submit for review. Google's review typically takes a few days
to a couple of weeks for a new listing.

## Updating the app later

Bump `appVersionCode` (integer, must increase every release) and
`appVersion` (the human-readable version string) in `twa-manifest.json`,
re-run `bubblewrap build`, and upload the new `.aab`. The site itself
(rooms4you.co.za) can keep shipping independently in the meantime — a TWA
has no bundled web content to go stale, it always loads the live site.

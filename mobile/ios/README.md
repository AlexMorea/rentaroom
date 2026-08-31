# Rooms4You — iOS app (Capacitor)

Same idea as `mobile/android`: wrap the live site (rooms4you.co.za) as a real
app, rather than maintaining a second codebase. `capacitor.config.json` points
`server.url` at `https://www.rooms4you.co.za` directly, so the app always
shows the live site — there's no bundled copy of the site to go stale.

The `ios/` folder in here is a **real, generated Xcode project** (via
`npx cap add ios`), not hand-written — it's exactly what running the same
command yourself would produce. It was generated in this environment because
Capacitor's project scaffolding is just file templating and doesn't need
Xcode to run; actually **building** it does.

## What's already done

- `capacitor.config.json` — app ID (`za.co.rooms4you.app`), app name, and
  `server.url` pointed at the live site
- `ios/` — the generated Xcode project (`ios/App/App.xcodeproj`)
- Push notification plugin config block already present in
  `capacitor.config.json` (presentation options for badge/sound/alert)

## What you need a Mac for

Nothing in this repo can get further than this without Xcode — Apple doesn't
allow building or signing iOS apps anywhere else. On a Mac:

```bash
cd mobile/ios
npm install
npx cap sync ios      # installs CocoaPods dependencies into ios/App/Pods
npx cap open ios      # opens ios/App/App.xcworkspace in Xcode
```

From Xcode: set your Apple Developer Team under Signing & Capabilities, pick
a real device or simulator, and Run. For a store build: Product → Archive,
then upload through Xcode Organizer or Transporter.

If a Mac isn't available to you, **Xcode Cloud** or a CI service like
Codemagic/Bitrise can build and sign from this same `mobile/ios` folder
without you owning a physical Mac — worth it once this is past prototyping.

## Push notifications on iOS — two different paths

This app already gets the same Web Push built for Android/the PWA
(`accounts/push.py`, `static/js/push-notify.js`) **for free, today, with no
App Store review**, via a route worth shipping in parallel with the Capacitor
app: iOS 16.4+ supports Web Push for a site added to the Home Screen through
Safari's native "Add to Home Screen" — no wrapper needed. Nudging iOS users
toward that (the existing `pwa-install.js`/install banner) gets them
notifications immediately.

Push *inside* the Capacitor-wrapped app is a separate mechanism — Apple's
WKWebView (what Capacitor uses) doesn't expose the same Push API a real
installed PWA gets, so the app-store app needs Apple Push Notification
service (APNs) via the `@capacitor/push-notifications` plugin plus an APNs
key from your Apple Developer account, wired to a second delivery path on
the Django side (not built yet — `accounts/push.py` today only speaks Web
Push/VAPID). Treat this as a fast-follow once the App Store listing exists,
not a blocker to shipping it.

## App Store submission

Separately from this repo, you'll need:

- An Apple Developer Program account (**$99/year**, real identity
  verification)
- App icon set (Xcode's asset catalog at
  `ios/App/App/Assets.xcassets` needs the full icon size range — export
  from `static/images/icon-512.png`)
- Screenshots for the device sizes App Store Connect requires
- A privacy policy URL (`/privacy/` already exists on the live site)
- App Privacy questionnaire in App Store Connect (what data the app
  collects — matches what the site already does: account info, location for
  Guardian safety sessions, no ad tracking)
- Store listing copy — reuse the same positioning as the Android listing
  (see `mobile/android/README.md`)

Submit via Xcode Organizer → Distribute App → App Store Connect, then finish
the listing in App Store Connect and submit for review. Apple's review is
typically 1–3 days for a new app.

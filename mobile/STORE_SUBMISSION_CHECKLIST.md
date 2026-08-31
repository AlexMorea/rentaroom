# Rooms4You — App Store & Play Store submission checklist

Everything code-side is done (see `mobile/android/` and `mobile/ios/`). What's
left is entirely human steps — accounts, payments, identity verification, and
store review — that nobody but the account owner can do. This is the
complete list, in the order to do them.

## Before either store

- [ ] Generate real VAPID keys for production and set them as env vars
      (`python manage.py generate_vapid_keys` — see `.env.example`).
      Without this, push notifications silently no-op in production.
- [ ] Confirm `rooms4you.co.za` is deployed with the changes in this branch
      (verified badges, in-app fraud reporting, push infra all need to be
      live before either app is submitted — a store reviewer testing the
      app is testing the live site through it).

## Android (Google Play)

1. [ ] Create a Google Play Developer account — **$25 one-time fee**, real
       ID verification. https://play.google.com/console/signup
2. [ ] On a machine with Node + a JDK: follow `mobile/android/README.md` to
       run `bubblewrap build`, producing a signed `.aab`.
   - [ ] **Save the keystore password somewhere durable and shared with
         whoever else might need to release an update.** Losing it means
         this exact app listing can never be updated again.
3. [ ] Get the SHA-256 fingerprint (`keytool -list -v ...`) and set
       `TWA_PACKAGE_NAME` / `TWA_SHA256_FINGERPRINTS` in production env vars.
       Confirm `https://www.rooms4you.co.za/.well-known/assetlinks.json`
       returns real data (not `[]`) before submitting — this is what makes
       the app open full-screen instead of showing a browser bar.
4. [ ] Prepare store listing assets: app icon (512×512), feature graphic
       (1024×500), 2+ phone screenshots, short + full description
       (draft in `mobile/android/README.md`), privacy policy URL
       (`https://www.rooms4you.co.za/privacy/`).
5. [ ] Complete the content rating questionnaire and data-safety section in
       Play Console (collects: account info, location for Guardian safety
       sessions and room search; no ad tracking).
6. [ ] Upload the `.aab` under Production → Create release, fill in the
       listing, submit for review.
7. [ ] Once approved: come back and enable `subscribe_pr_activity`-style
       monitoring isn't relevant here, but **do** watch for the first
       production push-notification delivery to confirm the Android app's
       notification delegation is actually working end-to-end.

## iOS (App Store)

1. [ ] Enroll in the Apple Developer Program — **$99/year**, real identity
       verification. https://developer.apple.com/programs/enroll/
2. [ ] On a Mac (or a cloud Mac CI like Xcode Cloud/Codemagic if one isn't
       available): follow `mobile/ios/README.md` to open the project in
       Xcode, set your Developer Team, and archive a release build.
3. [ ] Fill in the icon set in `ios/App/App/Assets.xcassets` (export from
       `static/images/icon-512.png`), and capture screenshots for the
       device sizes App Store Connect requires.
4. [ ] Complete the App Privacy questionnaire in App Store Connect (same
       data categories as Android: account info, location for Guardian
       sessions, no tracking).
5. [ ] Write the store listing (reuse the Android copy for consistency),
       link the privacy policy, submit through Xcode Organizer →
       Distribute App → App Store Connect, then submit for review there.
6. [ ] Optional fast-follow, not a launch blocker: wire real APNs push via
       `@capacitor/push-notifications` (see the "Push notifications on iOS"
       section of `mobile/ios/README.md`) — until then, iOS users get push
       today for free by adding the site to their Home Screen from Safari
       (iOS 16.4+), no store review needed.

## After both are live

- [ ] Update the homepage's "Why Rooms4You" section and the trust centre
      with real "Download on the App Store" / "Get it on Google Play"
      badges once both listings are approved — right now the site only
      promotes itself as a PWA.
- [ ] Point future marketing at the same differentiators used in the store
      listings: verified landlords (now actually visible), the safety
      escort (Guardian), the mover marketplace (Bakkie), and the
      pay-only-on-move-in model — the four things nothing else in this
      market combines.

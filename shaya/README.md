# Shaya: Mzansi's own short-video app (MVP)

Shaya is a short-video platform for South African creators: vertical swipe
feed, likes, comments, follows, sharing, and a **creator pay programme that
starts at 1,000 views** and pays out to any SA bank account through PayShap.

It exists because TikTok's Creator Rewards Programme is still not available
in South Africa. See [`docs/PROPOSAL.md`](docs/PROPOSAL.md) for the research,
the economics and the proposal to the Minister of Communications and Digital
Technologies.

> This folder is a standalone Django project. It shares nothing with the
> Rentaroom app in the parent directory.

## What works today

| Area | Feature |
| --- | --- |
| Feed | Full-screen vertical swipe feed with autoplay. *For You* (transparent engagement × freshness ranking) and *Following* tabs. Filter by any of the 12 official languages; search captions and #hashtags |
| Creating | Upload from phone camera or gallery (MP4/MOV/WEBM/3GP, up to 3 min / 60 MB), caption, language and province |
| Social | Likes, comments, follows, profiles, share to WhatsApp (or the phone's share sheet) with link previews |
| Data costs | **Data saver on by default**: ffmpeg makes a ~480p, ~600 kbps copy of every clip, and the feed doesn't preload clips you haven't reached |
| Pay | Paid-view tracking (3 s+ watch, not your own, one per viewer per 24 h), 1,000-view threshold, monthly revenue-share pool, creator studio with progress bars and earnings, PayShap withdrawals from R50 |
| Ads | Local advertisers buy sponsored clips at a CPM; one ad slot every 6 clips; advertisers are charged at most once per viewer per hour |
| Safety | Report button on every clip, admin moderation queue with one-click removal, under-13s blocked at sign-up, under-18s can't enter the paid programme (POPIA) |

## Run it

```bash
cd shaya
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo                       # needs ffmpeg; makes demo creators and clips
python manage.py close_month --month YYYY-MM     # the seed prints the right month
python manage.py createsuperuser                 # for /admin (moderation, ID verification, ads)
python manage.py runserver
```

Open http://127.0.0.1:8000 on your phone or in a mobile-sized browser window.
Demo login: `thandi_dances` / `shaya-demo-123`, then open **Studio**.

Tests: `python manage.py test clips`

## How creator pay is calculated

`clips/monetisation.py` is the whole engine and is meant to be read.

1. Every sponsored-clip impression is charged at the advertiser's CPM (held in
   thousandths of a cent so a R8.50 CPM isn't rounded away).
2. `close_month` takes **55%** of that month's ad revenue, plus any
   `FundTopUp` (sponsor, telco, grant), as the creator pool.
3. *Paid views* = qualified views that month, on clips with **≥ 1,000**
   lifetime qualified views, by creators who are 18+, ID-verified and have a
   PayShap ShapID.
4. The pool is split by paid views using the largest-remainder method, so the
   payouts always add up to exactly the pool, to the cent.

All the numbers are in `SHAYA` in `shaya_site/settings.py`.

The demo seed uses a realistic R30 CPM, and the result is the main finding of
this project: **ads alone pay about R3 per 1,000 views at SA ad rates.** The
proposal explains how the creator fund top-up closes that gap.

## Layout

```
shaya/
  clips/
    models.py          profiles, videos, social graph, views, ads, payouts
    monetisation.py    view qualification, ad charging, monthly pool, withdrawals
    media.py           ffprobe duration check and data-saver transcode
    views.py, urls.py  pages and JSON endpoints (view beacon, like, ad impression)
    management/commands/seed_demo.py, close_month.py
    tests.py
  templates/, static/shaya/   server-rendered HTML, one CSS file, one small JS file (no framework)
  docs/PROPOSAL.md            research, economics, roadmap and the ask to government
```

## What's not production-ready yet

* PayShap payouts are stubbed (`request_payout` creates the record; the bank
  call needs a PayShap-enabled bank or payments provider).
* ID verification is a staff checkbox; production needs a KYC provider that
  checks SA ID or Smart ID cards against Home Affairs.
* Transcoding runs inline on upload; production needs a job queue and a CDN
  (peered at NAPAfrica to keep delivery costs down).
* No native apps yet. The web app works on phones; Android comes first (see
  the roadmap).
* No licensed music library yet (needs SAMRO / CAPASSO / SAMPRA agreements).

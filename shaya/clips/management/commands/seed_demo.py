"""Fill a fresh database with demo creators, clips, an advertiser and views.

    python manage.py seed_demo

Clips are generated with ffmpeg (coloured test patterns with captions), so
no real people's content is used.
"""
import random
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from clips import media
from clips.models import AdCampaign, AdImpression, Comment, Follow, Like, Video, View

CREATORS = [
    ("thandi_dances", "Thandi", "GP", "zu", "Amapiano steps every Friday"),
    ("chef_sipho", "Chef Sipho", "KZN", "zu", "Kota, bunny chow and kasi kitchen hacks"),
    ("lerato_comedy", "Lerato", "LP", "nso", "Taxi rank comedy"),
    ("kaapse_klopse", "Riaan", "WC", "af", "Kaap se lekkerste"),
    ("mzansi_tech", "Ayanda", "EC", "xh", "Phone tips in isiXhosa"),
]
CAPTIONS = [
    "New dance challenge #amapiano #mzansi",
    "R50 kota that slaps #kasikitchen",
    "When the taxi driver says 'one more' #taxiranks",
    "Sunday braai prep #braai #lekker",
    "Save data on your phone #datasaver",
    "Load shedding survival kit #eskom",
    "Gqom vs Amapiano who wins? #music",
    "Learn 5 isiXhosa words #language",
]
COLOURS = ["0x007749", "0xffb612", "0xe03c31", "0x002395", "0x222222"]


def make_clip(path, colour, text):
    safe = "".join(ch for ch in text if ch.isalnum() or ch in " #")[:30]
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={colour}:s=360x640:d=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-vf", f"drawtext=text='{safe}':fontcolor=white:fontsize=22:x=(w-tw)/2:y=(h-th)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )


class Command(BaseCommand):
    help = "Create demo creators, clips, an ad campaign and simulated views."

    def handle(self, *args, **opts):
        if not shutil.which("ffmpeg"):
            raise CommandError("seed_demo needs ffmpeg to generate sample clips.")
        rng = random.Random(27)  # Freedom Day
        users = []
        for username, name, prov, lang, bio in CREATORS:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password("shaya-demo-123")
                user.save()
            p = user.profile
            p.display_name, p.province, p.language, p.bio = name, prov, lang, bio
            p.date_of_birth = date(1998, 4, 27)
            p.id_verified = True
            p.payout_shap_id = f"08{rng.randint(10000000, 99999999)}@demobank"
            p.save()
            users.append(user)

        videos = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, caption in enumerate(CAPTIONS):
                creator = users[i % len(users)]
                path = Path(tmp) / f"demo{i}.mp4"
                make_clip(path, COLOURS[i % len(COLOURS)], caption)
                with path.open("rb") as fh:
                    v = Video(creator=creator, caption=caption,
                              language=creator.profile.language, province=creator.profile.province)
                    v.file.save(path.name, File(fh), save=True)
                media.make_data_saver_copy(v)
                videos.append(v)
            path = Path(tmp) / "ad.mp4"
            make_clip(path, "0x111111", "Spaza Bank. Send money for R1")
            with path.open("rb") as fh:
                ad_video = Video(creator=users[4], caption="Open an account in 5 minutes")
                ad_video.file.save(path.name, File(fh), save=True)

        AdCampaign.objects.create(advertiser="Spaza Bank (demo)", video=ad_video,
                                  cpm_cents=3000, budget_cents=500_000)

        # Simulate last month's audience so the payout maths has data.
        now = timezone.now()
        last_month = (timezone.localdate().replace(day=1) - timedelta(days=1)).replace(day=1)
        mid_last_month = now - timedelta(days=now.day + 10)
        counts = [4200, 2600, 1800, 1300, 900, 400, 150, 60]
        for v, n in zip(videos, counts):
            View.objects.bulk_create([
                View(video=v, viewer_key=f"demo-{v.pk}-{k}", watch_ms=rng.randint(3000, 15000),
                     qualified=True, created_at=mid_last_month + timedelta(minutes=k))
                for k in range(n)
            ])
        # One ad slot per AD_EVERY_N_CLIPS clips watched, at the campaign's
        # R30 CPM: this is what ad sales alone pay at today's SA rates.
        campaign = AdCampaign.objects.get(video=ad_video)
        n_impressions = sum(counts) // settings.SHAYA["AD_EVERY_N_CLIPS"]
        AdImpression.objects.bulk_create([
            AdImpression(campaign=campaign, viewer_key=f"demo-ad-{k}",
                         cost_millicents=campaign.cpm_cents,
                         created_at=mid_last_month + timedelta(minutes=k))
            for k in range(n_impressions)
        ])
        campaign.spent_millicents = n_impressions * campaign.cpm_cents
        campaign.save(update_fields=["spent_millicents"])
        fans = []
        for k in range(12):
            fan, _ = User.objects.get_or_create(username=f"fan{k}")
            fans.append(fan)
            for v in rng.sample(videos, 3):
                Like.objects.get_or_create(user=fan, video=v)
            Follow.objects.get_or_create(follower=fan, following=rng.choice(users))
        for v in videos[:4]:
            Comment.objects.create(user=rng.choice(fans), video=v, text="Haibo this is fire 🔥")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(users)} creators and {len(videos)} clips. "
            "Log in as thandi_dances / shaya-demo-123. "
            f"Next: python manage.py close_month --month {last_month:%Y-%m}"
        ))

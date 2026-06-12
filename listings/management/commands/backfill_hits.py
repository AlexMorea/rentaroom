from django.core.management.base import BaseCommand
 
from django.db.models import Count
from listings.models import Room, RoomStat, Favorite, Review


class Command(BaseCommand):
    help = (
        "Backfill Room.hits from historical RoomStat and optional engagement metrics. "
        "Use --composite to include contacts/favorites/reviews. Use --force to apply updates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--composite",
            action="store_true",
            help="Compute composite hits = views + contacts*5 + favorites*2 + reviews*2",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Apply updates to DB. Without this flag the command only reports changes.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of updates to apply per batch",
        )

    def handle(self, *args, **options):
        composite = options["composite"]
        force = options["force"]
        batch_size = options["batch_size"]

        self.stdout.write("Computing counts from historical data...")

        views_qs = (
            RoomStat.objects.filter(stat_type="view")
            .values("room")
            .annotate(count=Count("id"))
        )
        views_map = {r["room"]: r["count"] for r in views_qs}

        contacts_map = {}
        favs_map = {}
        revs_map = {}

        if composite:
            contacts_qs = (
                RoomStat.objects.filter(stat_type__startswith="contact")
                .values("room")
                .annotate(count=Count("id"))
            )
            contacts_map = {r["room"]: r["count"] for r in contacts_qs}

            favs_qs = (
                Favorite.objects.values("room").annotate(count=Count("id"))
            )
            favs_map = {r["room"]: r["count"] for r in favs_qs}

            revs_qs = (
                Review.objects.values("room").annotate(count=Count("id"))
            )
            revs_map = {r["room"]: r["count"] for r in revs_qs}

        total_rooms = Room.objects.count()
        self.stdout.write(f"Preparing updates for {total_rooms} rooms (composite={composite})")

        to_update = []
        processed = 0

        qs = Room.objects.all().order_by("id")

        for room in qs.iterator():
            v = views_map.get(room.id, 0)
            if composite:
                c = contacts_map.get(room.id, 0)
                f = favs_map.get(room.id, 0)
                r = revs_map.get(room.id, 0)
                hits_val = v + (c * 5) + (f * 2) + (r * 2)
            else:
                hits_val = v

            if room.hits != hits_val:
                to_update.append((room.id, hits_val))

            if len(to_update) >= batch_size:
                if force:
                    for rid, hv in to_update:
                        Room.objects.filter(pk=rid).update(hits=hv)
                    processed += len(to_update)
                    self.stdout.write(f"Applied {processed}/{total_rooms} updates...")
                else:
                    self.stdout.write(f"Prepared {len(to_update)} updates (use --force to apply)")
                to_update.clear()

        # final batch
        if to_update:
            if force:
                for rid, hv in to_update:
                    Room.objects.filter(pk=rid).update(hits=hv)
                processed += len(to_update)
                self.stdout.write(f"Applied {processed}/{total_rooms} updates...")
            else:
                self.stdout.write(f"Prepared {len(to_update)} updates (use --force to apply)")

        self.stdout.write(self.style.SUCCESS("Backfill complete."))

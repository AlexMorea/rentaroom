from django.core.management.base import BaseCommand
from django.db.models import Count

from listings.models import Room, RoomStat


class Command(BaseCommand):
    help = "Compute and store materialized score for rooms. Use --force to apply updates."

    def add_arguments(self, parser):
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
        force = options["force"]
        batch_size = options["batch_size"]

        self.stdout.write("Computing engagement aggregates...")

        qs = (
            Room.objects.all()
            .annotate(
                views_count=Count(
                    "roomstat",
                    filter=RoomStat.objects.filter(stat_type="view").query,
                ),
                contacts_count=Count(
                    "roomstat",
                    filter=RoomStat.objects.filter(stat_type__startswith="contact").query,
                ),
                favorites_count=Count("favorited_by"),
                reviews_count=Count("reviews"),
            )
        )

        to_update = []
        processed = 0

        for room in qs.iterator():
            score = (
                (room.hits or 0) * 3
                + (room.views_count or 0) * 1
                + (room.contacts_count or 0) * 8
                + (room.favorites_count or 0) * 2
                + (room.reviews_count or 0) * 2
            )

            if room.score != score:
                to_update.append((room.id, score))

            if len(to_update) >= batch_size:
                if force:
                    for rid, sc in to_update:
                        Room.objects.filter(pk=rid).update(score=sc)
                    processed += len(to_update)
                    self.stdout.write(f"Applied {processed} updates so far...")
                else:
                    self.stdout.write(f"Prepared {len(to_update)} updates (use --force to apply)")
                to_update.clear()

        if to_update:
            if force:
                for rid, sc in to_update:
                    Room.objects.filter(pk=rid).update(score=sc)
                processed += len(to_update)
                self.stdout.write(f"Applied {processed} updates in total.")
            else:
                self.stdout.write(f"Prepared {len(to_update)} updates (use --force to apply) ")

        self.stdout.write(self.style.SUCCESS("Score computation finished."))

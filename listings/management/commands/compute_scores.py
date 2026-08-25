from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Sum

from listings.models import Room


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
                    filter=Q(roomstat__stat_type="view"),
                ),
                contacts_count=Count(
                    "roomstat",
                    filter=Q(roomstat__stat_type__startswith="contact"),
                ),
                favorites_count=Count("favorited_by"),
                reviews_count=Count("reviews"),
                reviews_rating_sum=Sum("reviews__rating"),
            )
        )

        to_update = []
        processed = 0

        for room in qs.iterator():
            # Rating-weighted, not just a raw review count - a room's reviews
            # only used to count toward score regardless of whether they were
            # good or bad, which meant a string of 1-star reviews boosted
            # ranking exactly like 5-star ones. Centered on 3 (neutral) so
            # above-average reviews add score and below-average ones
            # subtract from it - the review system actually has to mean
            # something to the ranking.
            review_quality = (room.reviews_rating_sum or 0) - (room.reviews_count * 3)

            score = (
                (room.hits or 0) * 3
                + (room.views_count or 0) * 1
                + (room.contacts_count or 0) * 8
                + (room.favorites_count or 0) * 2
                + review_quality * 3
            )
            # score is a PositiveIntegerField - a room with mostly poor
            # reviews and little other engagement could otherwise compute
            # negative here.
            score = max(0, score)

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

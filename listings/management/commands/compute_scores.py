from django.conf import settings
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

        # reviews_count/reviews_rating_sum are deliberately annotated in
        # their OWN query, not alongside views/contacts/favorites below.
        # Combining a Sum with Counts over a *different* reverse relation
        # in one annotate() call joins both tables before aggregating,
        # which silently inflates every aggregate by the other relation's
        # row count (e.g. 1 real review reads back as 4 once a room also
        # has 4 RoomStat rows) - Count can be corrected with
        # distinct=True, but Sum(distinct=True) sums distinct *values*,
        # not distinct rows, so two 5-star reviews would collapse into
        # one 5 instead of 10. Keeping this Sum in its own single-relation
        # query sidesteps the fan-out entirely rather than papering over
        # it. Verified against raw SQL during development.
        review_stats = {
            row["id"]: row
            for row in Room.objects.values("id").annotate(
                reviews_count=Count("reviews"),
                reviews_rating_sum=Sum("reviews__rating"),
            )
        }

        qs = (
            Room.objects.all()
            .annotate(
                views_count=Count(
                    "roomstat",
                    filter=Q(roomstat__stat_type="view"),
                    distinct=True,
                ),
                contacts_count=Count(
                    "roomstat",
                    filter=Q(roomstat__stat_type__startswith="contact"),
                    distinct=True,
                ),
                favorites_count=Count("favorited_by", distinct=True),
            )
        )

        to_update = []
        processed = 0
        stale_count = 0

        for room in qs.iterator():
            review_row = review_stats.get(room.id, {})
            reviews_count = review_row.get("reviews_count") or 0
            reviews_rating_sum = review_row.get("reviews_rating_sum") or 0

            # Rating-weighted, not just a raw review count - a room's reviews
            # only used to count toward score regardless of whether they were
            # good or bad, which meant a string of 1-star reviews boosted
            # ranking exactly like 5-star ones. Centered on 3 (neutral) so
            # above-average reviews add score and below-average ones
            # subtract from it - the review system actually has to mean
            # something to the ranking.
            review_quality = reviews_rating_sum - (reviews_count * 3)

            score = (
                (room.hits or 0) * 3
                + (room.views_count or 0) * 1
                + (room.contacts_count or 0) * 8
                + (room.favorites_count or 0) * 2
                + review_quality * 3
            )

            # A listing nobody's confirmed in a while shouldn't keep
            # competing for the same ranking as one that's actually
            # current - soft demotion (grows with how overdue it is,
            # capped) rather than a hard cliff, so it fades rather than
            # vanishing the instant it crosses the threshold.
            if room.is_stale:
                stale_count += 1
                score -= min(room.days_since_confirmed - settings.LISTING_STALE_DAYS, 60) * 2

            # score is a PositiveIntegerField - a room with mostly poor
            # reviews/little engagement, or a heavily stale one, could
            # otherwise compute negative here.
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

        if stale_count:
            self.stdout.write(f"{stale_count} listing(s) received a staleness penalty.")

        self.stdout.write(self.style.SUCCESS("Score computation finished."))

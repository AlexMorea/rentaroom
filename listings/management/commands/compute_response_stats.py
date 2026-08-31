from statistics import median

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from listings.models import Message, Profile

# Only recent threads count, so this reflects how a landlord behaves NOW,
# not a burst of fast replies from months ago that no longer means
# anything (or a bad week that unfairly follows them forever).
RESPONSE_WINDOW_DAYS = 90


class Command(BaseCommand):
    help = (
        "Compute each landlord's median response time and response rate "
        "from real Message threads (tenant's first message -> landlord's "
        "first reply). Use --force to apply updates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Apply updates to DB. Without this flag the command only reports changes.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        since = timezone.now() - timezone.timedelta(days=RESPONSE_WINDOW_DAYS)

        landlords = Profile.objects.filter(role="landlord").select_related("user")

        to_update = []

        for profile in landlords:
            landlord_id = profile.user_id

            messages = (
                Message.objects.filter(created_at__gte=since)
                .filter(Q(sender_id=landlord_id) | Q(recipient_id=landlord_id))
                .order_by("created_at")
                .values("room_id", "sender_id", "recipient_id", "created_at")
            )

            # One "thread" per (room, tenant) pair - matches how
            # conversation_thread already scopes a conversation. Walking
            # messages in chronological order and only ever recording the
            # FIRST tenant message and the FIRST landlord message after it
            # is what makes this "time to first reply", not just "time
            # between any two messages".
            threads = {}
            for m in messages:
                is_from_landlord = m["sender_id"] == landlord_id
                other_id = m["recipient_id"] if is_from_landlord else m["sender_id"]
                thread = threads.setdefault(
                    (m["room_id"], other_id), {"tenant_first": None, "landlord_reply": None}
                )

                if is_from_landlord:
                    if thread["tenant_first"] is not None and thread["landlord_reply"] is None:
                        thread["landlord_reply"] = m["created_at"]
                elif thread["tenant_first"] is None:
                    thread["tenant_first"] = m["created_at"]

            response_minutes = []
            replied = 0
            total_threads = 0

            for thread in threads.values():
                if thread["tenant_first"] is None:
                    continue  # landlord-initiated only - not a tenant enquiry to respond to
                total_threads += 1
                if thread["landlord_reply"]:
                    replied += 1
                    delta = thread["landlord_reply"] - thread["tenant_first"]
                    response_minutes.append(max(int(delta.total_seconds() // 60), 0))

            if total_threads == 0:
                # No recent tenant enquiries - reset rather than leave a
                # stale claim standing from outside the measurement window.
                avg_minutes, rate = None, None
            else:
                avg_minutes = int(median(response_minutes)) if response_minutes else None
                rate = round((replied / total_threads) * 100)

            current = (profile.avg_response_minutes, profile.response_rate_percent, profile.responses_measured)
            new = (avg_minutes, rate, total_threads)

            if current != new:
                to_update.append((profile.pk, *new))

        self.stdout.write(f"{len(to_update)} landlord profile(s) to update.")

        if not force:
            for pk, avg_minutes, rate, total_threads in to_update:
                self.stdout.write(
                    f"  [would update] profile#{pk}: avg={avg_minutes}min rate={rate}% threads={total_threads}"
                )
            self.stdout.write(self.style.WARNING("Dry run only - use --force to apply."))
            return

        for pk, avg_minutes, rate, total_threads in to_update:
            Profile.objects.filter(pk=pk).update(
                avg_response_minutes=avg_minutes,
                response_rate_percent=rate,
                responses_measured=total_threads,
            )

        self.stdout.write(self.style.SUCCESS(f"Updated {len(to_update)} landlord profile(s)."))

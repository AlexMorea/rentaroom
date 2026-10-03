from datetime import date

from django.core.management.base import BaseCommand, CommandError

from clips.monetisation import close_month, previous_month


class Command(BaseCommand):
    help = "Close a month's creator pool and calculate everyone's earnings (default: last month)."

    def add_arguments(self, parser):
        parser.add_argument("--month", help="YYYY-MM (defaults to the previous month)")

    def handle(self, *args, **opts):
        if opts["month"]:
            try:
                year, month = map(int, opts["month"].split("-"))
                target = date(year, month, 1)
            except ValueError as exc:
                raise CommandError("Use --month YYYY-MM") from exc
        else:
            target = previous_month()
        period = close_month(target)
        self.stdout.write(
            f"{period}: ad revenue R{period.ad_revenue_cents / 100:.2f}, "
            f"top-ups R{period.top_up_cents / 100:.2f}, pool R{period.creator_pool_cents / 100:.2f}, "
            f"{period.paid_views} paid views, R{period.rate_per_1000_cents / 100:.2f} per 1,000, "
            f"{period.earnings.count()} creators paid"
        )

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete unverified users after 24 hours"

    def handle(self, *args, **kwargs):
        cutoff = timezone.now() - timedelta(hours=24)

        users = User.objects.filter(
            is_active=False,
            date_joined__lt=cutoff
        )

        count = users.count()
        users.delete()

        self.stdout.write(f"Deleted {count} unverified users")
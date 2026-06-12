from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from listings.models import Profile

User = get_user_model()


class Command(BaseCommand):
    help = "Create Profile objects for Users missing them"

    def handle(self, *args, **options):
        users = User.objects.all()
        created = 0
        for u in users:
            profile, was_created = Profile.objects.get_or_create(user=u)
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} profiles."))

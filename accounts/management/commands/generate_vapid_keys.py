from django.core.management.base import BaseCommand

from accounts.push import generate_ephemeral_vapid_keys


class Command(BaseCommand):
    help = (
        "Generate a real VAPID keypair for production Web Push. Run this "
        "ONCE, then set VAPID_PRIVATE_KEY_PEM and VAPID_PUBLIC_KEY as env "
        "vars wherever the app is deployed. Rotating the keys later "
        "invalidates every push subscription collected under the old pair "
        "(users would need to re-enable notifications)."
    )

    def handle(self, *args, **options):
        private_pem, public_b64url = generate_ephemeral_vapid_keys()

        self.stdout.write(self.style.SUCCESS("Generated a new VAPID keypair.\n"))
        self.stdout.write(
            "Set these as environment variables (e.g. in Render's dashboard "
            "or a production .env - never commit them to git):\n"
        )
        self.stdout.write("\nVAPID_PUBLIC_KEY=" + public_b64url)
        self.stdout.write(
            "\nVAPID_PRIVATE_KEY_PEM=\"" + private_pem.replace("\n", "\\n") + "\"\n"
        )
        self.stdout.write(
            self.style.WARNING(
                "\nThe private key above is a PEM block with real newlines - "
                "if your env var format doesn't support that, keep the "
                "\\n-escaped one-liner shown here; accounts/push.py doesn't "
                "need to un-escape it since pywebpush/py_vapid accept it as-is."
            )
        )

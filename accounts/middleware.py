from django.db import IntegrityError, OperationalError

from .models import Membership

try:
    # import lazily to avoid circular imports during project setup
    from listings.models import Profile
except ImportError:
    Profile = None


class MembershipMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:
            # Ensure a Profile exists for the authenticated user to avoid
            # AttributeError when templates or views access `user.profile`.
            if Profile is not None:
                try:
                    Profile.objects.get_or_create(user=request.user)
                except (IntegrityError, OperationalError):
                    # best-effort only; don't block request on DB errors
                    pass

            try:
                if request.user.profile.role == "landlord":

                    membership = (
                        Membership.objects
                        .filter(user=request.user)
                        .only(
                            "is_trial",
                            "is_active",
                            "trial_end"
                        )
                        .first()
                    )

                    if (
                        membership
                        and membership.is_trial
                        and membership.is_trial_expired()
                    ):
                        membership.is_active = False
                        membership.save(
                            update_fields=["is_active"]
                        )

            except AttributeError:
                pass

        return self.get_response(request)
from .models import Membership


class MembershipMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:
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
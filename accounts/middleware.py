from .models import Membership


class MembershipMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:
            try:
                membership, _ = Membership.objects.get_or_create(user=request.user)

                # Trial expired → downgrade
                if membership.is_trial and membership.is_trial_expired():
                    membership.is_active = False
                    membership.save()

            except Membership.DoesNotExist:
                pass

        return self.get_response(request)
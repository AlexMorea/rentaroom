from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from accounts.decorators import require_state
from accounts.state_engine import evaluate_user_state


class EvaluateUserStateTests(TestCase):
    """
    accounts/decorators.py imports evaluate_user_state from this module -
    previously that function didn't exist, so importing the decorator would
    raise ImportError. Covers the function directly (unauthenticated,
    authenticated-but-unverified, authenticated-and-verified) plus the
    decorator wiring it into.
    """

    def test_anonymous_user_is_blocked_to_login(self):
        state = evaluate_user_state(AnonymousUser())
        self.assertTrue(state.blocked)
        self.assertEqual(state.next_route, "login")

    def test_unverified_user_is_blocked_to_verify_account(self):
        user = User.objects.create_user(username="unverified", email="unverified@example.com", password="pass")
        state = evaluate_user_state(user)
        self.assertTrue(state.blocked)
        self.assertEqual(state.next_route, "verify_account")

    def test_verified_user_is_not_blocked(self):
        user = User.objects.create_user(username="verified", email="verified@example.com", password="pass")
        user.profile.is_phone_verified = True
        user.profile.is_email_verified = True
        user.profile.save()

        state = evaluate_user_state(user)
        self.assertFalse(state.blocked)
        self.assertEqual(state.next_route, "room_list")

    def test_require_state_decorator_imports_and_runs(self):
        @require_state
        def dummy_view(request):
            return "ok"

        class FakeRequest:
            user = AnonymousUser()

        result = dummy_view(FakeRequest())
        # Blocked anonymous user gets redirected instead of reaching the view
        self.assertNotEqual(result, "ok")

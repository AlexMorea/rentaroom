from dataclasses import dataclass

from services.models import BakkieDriver


@dataclass
class UserState:
    blocked: bool
    next_route: str


def evaluate_user_state(user):
    """
    Thin wrapper around get_user_state() for the require_state decorator:
    gates access for unauthenticated or unverified users, otherwise lets
    the request through and reports where get_user_state() would route them.
    """
    if not user.is_authenticated:
        return UserState(blocked=True, next_route="login")

    state = get_user_state(user)

    if not state["verified"]:
        return UserState(blocked=True, next_route="verify_account")

    return UserState(blocked=False, next_route=state["next_route"])


def get_user_state(user):
    """
    Single source of truth for user routing.
    """

    profile = user.profile

    state = {
        "authenticated": user.is_authenticated,
        "verified": (
            profile.is_email_verified
            and profile.is_phone_verified
        ),
        "role": profile.role,
        "profile_complete": profile_is_complete(user),
        "driver": None,
        "next_route": "room_list",
    }

    # ---------------- DRIVER ----------------
    if profile.role == "driver":
        driver = BakkieDriver.objects.filter(
            user=user
        ).first()

        state["driver"] = driver

        if not driver or not driver.is_verified:
            state["next_route"] = "services:bakkie_home"

        else:
            state["next_route"] = "services:driver_dashboard"

    # ---------------- LANDLORD ----------------
    elif profile.role == "landlord":
        state["next_route"] = "dashboard"

    # ---------------- TENANT ----------------
    else:
        state["next_route"] = "room_list"

    return state


def profile_is_complete(user):
    p = user.profile

    if p.role == "tenant":
        return bool(p.persona)

    if p.role == "landlord":
        return bool(
            p.phone_number
            and p.home_address
        )

    return p.role == "driver"
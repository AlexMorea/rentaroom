import secrets

SAFE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ234679"


def generate_membership_id():
    return "R4Y" + "".join(
        secrets.choice(SAFE_CHARS)
        for _ in range(6)
    )
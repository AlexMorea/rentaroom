from functools import wraps

from django.shortcuts import redirect

from accounts.state_engine import evaluate_user_state


def require_state(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        state = evaluate_user_state(request.user)

        if state.blocked:
            return redirect(state.next_route)

        return view_func(request, *args, **kwargs)

    return wrapper
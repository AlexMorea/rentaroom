import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import PushSubscription


@login_required
@require_POST
def push_subscribe(request):
    try:
        payload = json.loads(request.body or "{}")
        endpoint = payload["endpoint"]
        keys = payload["keys"]
        p256dh = keys["p256dh"]
        auth = keys["auth"]
    except (KeyError, ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid subscription payload."}, status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
        },
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        payload = json.loads(request.body or "{}")
        endpoint = payload["endpoint"]
    except (KeyError, ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid payload."}, status=400)

    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({"ok": True})
